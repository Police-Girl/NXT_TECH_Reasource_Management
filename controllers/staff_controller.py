# controllers/staff_controller.py - CONTROLLER for staff pages and request submission.
# Admins cannot submit staff requests and are redirected to /admin.

from flask import Blueprint, flash, redirect, render_template, request
from flask_login import current_user, login_required

from models.inventory_model import get_all_inventory
from models.notification_model import create_notification
from models.request_model import create_request, get_requests_by_user

# Blueprint managing staff views, request creation, and personal request status history
staff_bp = Blueprint("staff", __name__)

# Valid request category keys corresponding to Cosmos DB 'requests' partition values (/request_type)
REQUEST_TYPES = {
    "equipment",
    "office_items",
    "meeting_room",
    "tea_catering",
    "field_day",
    "appliance",
}

# Maps UI category labels or inv_category_filter values into canonical REQUEST_TYPES keys
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
}


def _normalize_request_type(raw_value: str) -> str:
    """Normalize labels like 'Equipment' or 'Office Items' into snake_case keys."""
    cleaned = (raw_value or "").strip().lower().replace("-", "_").replace(" ", "_")
    return CATEGORY_TO_REQUEST_TYPE.get(cleaned, cleaned)


def _extract_items_needed(form) -> str:
    """Collect selected items from multi-value fields, text inputs, or fallback names."""
    values = [v.strip() for v in form.getlist("items_needed") if v and v.strip()]
    if values:
        return ", ".join(values)
    # Fallback in case an HTML form uses 'items' or 'item' as the input name
    return (form.get("items") or form.get("item") or "").strip()


@staff_bp.route("/")
@login_required
def index():
    """Render the staff workspace form, inventory options, and the staff user's requests."""
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
    """Validate form inputs, persist the request to Cosmos DB, and notify admins in-app."""
    if current_user.role == "admin":
        flash("Admins cannot submit requests.", "error")
        return redirect("/admin")

    # Prefer explicit request_type; fall back to inv_category_filter when that select is used
    raw_type = request.form.get("request_type") or request.form.get("inv_category_filter") or ""
    request_type = _normalize_request_type(raw_type)
    # Default blank or 'all' filter values to 'office_items' so a valid partition key is used
    if request_type in ("", "all"):
        request_type = "office_items"

    items = _extract_items_needed(request.form)
    date = (request.form.get("date") or "").strip()
    time = (request.form.get("time") or "").strip()
    end_time = (request.form.get("end_time") or "").strip()
    venue = (request.form.get("venue") or "").strip() or "N/A"

    # Reject incomplete submissions or unsupported request categories
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

    # Ensure the requested time slot ends after it starts
    if end_time <= time:
        flash("End time must be later than the start time.", "error")
        return redirect("/")

    # Store custom venue only for field_day bookings; otherwise standardize to 'N/A'
    final_venue = venue if request_type == "field_day" else "N/A"

    # Pull identity from the logged-in session rather than trusting hidden form fields
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

    # Record an in-platform notification in Cosmos DB for admin review
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
    """Show the current staff user's submitted requests and their approval statuses."""
    if current_user.role == "admin":
        return redirect("/admin")
    return render_template(
        "staff/my_requests.html",
        requests=get_requests_by_user(current_user.work_id),
    )