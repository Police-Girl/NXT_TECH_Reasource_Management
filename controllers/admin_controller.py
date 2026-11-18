# controllers/admin_controller.py - CONTROLLER for everything admin-only.

from functools import wraps

from flask import Blueprint, flash, jsonify, redirect, render_template, request
from flask_login import current_user, login_required

from mailer import send_notification
from models.inventory_model import (
    CATEGORIES, create_inventory_item, delete_inventory_item,
    get_all_inventory, update_inventory_quantity,
)
from models.request_model import (
    find_conflicts, get_all_requests, get_item_counts,
    get_request, get_type_counts, set_request_status,
)
from models.user_model import get_user_by_work_id

admin_bp = Blueprint("admin", __name__)


def admin_required(view):
    """Block anyone who is not an admin. Always stack it UNDER @login_required."""
    @wraps(view)
    def wrapper(*args, **kwargs):
        if current_user.role != "admin":
            flash("Access denied.", "error")
            return redirect("/")
        return view(*args, **kwargs)
    return wrapper


# ---------------------------------------------------------------- dashboard
@admin_bp.route("/admin")
@login_required
@admin_required
def dashboard():
    """Stats, charts and the requests table. ?filter=pending|approved|rejected narrows the table."""
    all_requests = get_all_requests()
    status = request.args.get("filter")
    if status in ("pending", "approved", "rejected"):
        table_requests = [r for r in all_requests if r.get("status") == status]
    else:
        table_requests = all_requests

    return render_template(
        "admin/dashboard.html",
        requests=all_requests,          # used for the stat cards
        table_requests=table_requests,  # used for the table
        type_counts=get_type_counts(all_requests),
        item_counts=get_item_counts(all_requests),
    )


# ---------------------------------------------------------------- approve / reject
def _notify(item, status):
    """Email the staff member. Returns True if the email went out."""
    user = get_user_by_work_id(item["work_id"])
    if user and user.get("email"):
        return send_notification(user["email"], item["name"], item["request_type"], status)
    return False


@admin_bp.route("/admin/approve/<request_id>/<request_type>")
@login_required
@admin_required
def approve(request_id, request_type):
    try:
        item = get_request(request_id, request_type)
    except Exception:
        flash("Request not found.", "error")
        return redirect("/admin")

    if item.get("status") != "pending":
        flash("That request has already been actioned.", "error")
        return redirect("/admin")

    # Refuse to double-book: same item, same day, overlapping time.
    conflicts = find_conflicts(item)
    if conflicts:
        other, shared = conflicts[0]
        flash(
            f"Cannot approve: {', '.join(sorted(shared))} already booked by {other['name']} "
            f"on {other['date']} from {other['time']} to {other.get('end_time', '?')}.",
            "error",
        )
        return redirect("/admin")

    set_request_status(item, "approved")
    if _notify(item, "approved"):
        flash("Request approved and staff notified by email.", "success")
    else:
        flash("Request approved (email could not be sent).", "success")
    return redirect("/admin")


@admin_bp.route("/admin/reject/<request_id>/<request_type>")
@login_required
@admin_required
def reject(request_id, request_type):
    try:
        item = get_request(request_id, request_type)
    except Exception:
        flash("Request not found.", "error")
        return redirect("/admin")

    if item.get("status") != "pending":
        flash("That request has already been actioned.", "error")
        return redirect("/admin")

    set_request_status(item, "rejected")
    if _notify(item, "rejected"):
        flash("Request rejected and staff notified by email.", "error")
    else:
        flash("Request rejected (email could not be sent).", "error")
    return redirect("/admin")


# ---------------------------------------------------------------- inventory
@admin_bp.route("/admin/inventory")
@login_required
@admin_required
def inventory():
    """Read-only stock view."""
    return render_template("admin/inventory.html", items=get_all_inventory())


@admin_bp.route("/admin/inventory/data")
@login_required
@admin_required
def inventory_data():
    """JSON feed for the dashboard's inventory cards."""
    return jsonify(get_all_inventory())


@admin_bp.route("/admin/inventory/edit", methods=["GET", "POST"])
@login_required
@admin_required
def inventory_edit():
    """GET shows the editor. POST adds a new item."""
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        category = request.form.get("category", "")
        try:
            quantity = int(request.form.get("quantity", 0))
        except ValueError:
            quantity = -1
        if not name or category not in CATEGORIES or quantity < 0:
            flash("Enter a name, a category and a quantity of 0 or more.", "error")
        else:
            create_inventory_item(name, category, quantity)
            flash(f"{name} added to inventory.", "success")
        return redirect("/admin/inventory/edit")

    return render_template("admin/inventory_edit.html", items=get_all_inventory(), categories=CATEGORIES)


@admin_bp.route("/admin/inventory/update/<item_id>/<category>", methods=["POST"])
@login_required
@admin_required
def inventory_update(item_id, category):
    try:
        update_inventory_quantity(item_id, category, int(request.form.get("quantity", 0)))
        flash("Quantity updated.", "success")
    except Exception:
        flash("Could not update that item.", "error")
    return redirect("/admin/inventory/edit")


@admin_bp.route("/admin/inventory/delete/<item_id>/<category>", methods=["POST"])
@login_required
@admin_required
def inventory_delete(item_id, category):
    try:
        delete_inventory_item(item_id, category)
        flash("Item removed from inventory.", "success")
    except Exception:
        flash("Could not delete that item.", "error")
    return redirect("/admin/inventory/edit")
