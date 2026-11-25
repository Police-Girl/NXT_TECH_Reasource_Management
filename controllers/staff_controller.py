# controllers/staff_controller.py
# Controller for staff workspace views, resource request submission, and personal request history.
# Admin users are redirected to /admin so they cannot submit staff-side requests.

from flask import Blueprint, flash, redirect, render_template, request
from flask_login import current_user, login_required

from models.inventory_model import get_all_inventory
from models.notification_model import create_notification
from models.request_model import create_request, get_requests_by_user

# Blueprint handling staff routes and request submissions
staff_bp = Blueprint("staff", __name__)

# Allowed request category keys matching Cosmos DB 'requests' partition values (/request_type)
REQUEST_TYPES = {
    "equipment",
    "office_items",
    "meeting_room",
    "tea_catering",
    "field_day",
    "appliance",
    "vehicles",
}

# Maps UI category labels or inv_category_filter values to canonical REQUEST_TYPES keys
CATEGORY_TO_REQUEST_TYPE = {
    "equipment": "equipment",
    "office_items": "office_items",
    "office": "office_items",
    "meeting_room": "meeting_room",
    "meeting_rooms": "meeting_room",
    "tea_catering": "tea_catering",
    "catering": "tea_catering",
    "field_day": "field_day",
    "appliance": "appliance",
    "appliances": "appliance",
    "vehicles": "vehicles",
    "vehicle": "vehicles",
}


def _normalize_request_type(raw_value: str) -> str:
    """Normalize raw category strings (e.g. 'Vehicles' or 'Office Items') into snake_case keys."""
    cleaned = (raw_value or "").strip().lower().replace("-", "_").replace(" ", "_")
    return CATEGORY_TO_REQUEST_TYPE.get(cleaned, cleaned)


def _extract_items_needed(form) -> str:
    """Extract requested item names from multi-value inputs or fallback field names."""
    values = [v.strip() for v in form.getlist("items_needed") if v and v.strip()]
    if values:
        return ", ".join(values)

    # Support alternate single-value field names if a form variant uses 'items' or 'item'
    return (form.get("items") or form.get("item") or "").strip()


@staff_bp.route("/")
@login_required
def index():
    """Render the staff request form, available inventory, and the user's existing requests."""
    if current_user.role == "admin":
        return redirect("/admin")

    return render_template(
        "staff/index.html",
        inventory_items=get_all_inventory(),
        my_requests=get_requests_by_user(current_user.work_id),
    )


@staff_bp.route("/submit", methods=["POST"])
@login_required
def submit():
    """Validate staff request fields, save to Cosmos DB, and notify admins in-app."""
    if current_user.role == "admin":
        flash("Admins cannot submit requests.", "error")
        return redirect("/admin")

    # Use explicit request_type when present; otherwise fall back to inv_category_filter
    raw_type = request.form.get("request_type") or request.form.get("inv_category_filter") or ""
    request_type = _normalize_request_type(raw_type)

    # Default empty or 'all' selections to 'office_items' so a valid partition key is stored
    if request_type in ("", "all"):
        request_type = "office_items"

    items = _extract_items_needed(request.form)
    date = (request.form.get("date") or "").strip()
    time = (request.form.get("time") or "").strip()
    end_time = (request.form.get("end_time") or "").strip()
    venue = (request.form.get("venue") or "").strip() or "N/A"

    # Reject missing required inputs or categories outside REQUEST_TYPES
    if request_type not in REQUEST_TYPES or not (items and date and time and end_time):
        print(
            "[staff.submit] Validation failed:",
            {
                "raw_type": raw_type,
                "normalized_type": request_type,
                "items_needed": items,
                "date": date,
                "time": time,
                "end_time": end_time,
                "form_keys": list(request.form.keys()),
            },
        )
        flash("Please complete every required field.", "error")
        return redirect("/")

    # Reject non-positive or inverted time windows
    if end_time <= time:
        flash("End time must be later than the start time.", "error")
        return redirect("/")

    # Preserve custom venue only for field_day requests; normalize all other types to 'N/A'
    final_venue = venue if request_type == "field_day" else "N/A"

    # Derive requester identity from the authenticated session rather than client form inputs
    create_request(
        name=current_user.name,
        work_id=current_user.work_id,
        request_type=request_type,
        items_needed=items,
        date=date,
        time=time,
        end_time=end_time,
        venue=final_venue,
    )

    # Create an admin notification so pending requests appear in the admin alert feed
    create_notification(
        recipient_role="admin",
        message=(
            f"New {request_type.replace('_', ' ')} request from "
            f"{current_user.name} ({current_user.work_id}) for {items} on {date} ({time}-{end_time})."
        ),
        target_work_id=None,
        link="/admin",
    )

    flash("Request submitted successfully.", "success")
    return redirect("/")


@staff_bp.route("/my-requests")
@login_required
def my_requests():
    """Display the logged-in staff member's submitted requests and approval statuses."""
    if current_user.role == "admin":
        return redirect("/admin")

    return render_template(
        "staff/my_requests.html",
        requests=get_requests_by_user(current_user.work_id),
    )