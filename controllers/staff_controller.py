# controllers/staff_controller.py - CONTROLLER for staff pages.
# Admins cannot submit requests, so every route bounces them to /admin.

from flask import Blueprint, flash, redirect, render_template, request
from flask_login import current_user, login_required

from models.request_model import create_request, get_requests_by_user

staff_bp = Blueprint("staff", __name__)

REQUEST_TYPES = {"office_items", "meeting_room", "tea_catering", "field_day", "appliance"}


@staff_bp.route("/")
@login_required
def index():
    """The request form."""
    if current_user.role == "admin":
        return redirect("/admin")
    return render_template("staff/index.html")


@staff_bp.route("/submit", methods=["POST"])
@login_required
def submit():
    """Validate the form, hand the data to the model, go back to the form."""
    if current_user.role == "admin":
        flash("Admins cannot submit requests.", "error")
        return redirect("/admin")

    request_type = request.form.get("request_type", "")
    items = request.form.get("items_needed", "").strip()
    date = request.form.get("date", "")
    time = request.form.get("time", "")
    end_time = request.form.get("end_time", "")
    venue = request.form.get("venue", "").strip() or "N/A"

    if request_type not in REQUEST_TYPES or not (items and date and time and end_time):
        flash("Please complete every required field.", "error")
        return redirect("/")
    if end_time <= time:
        flash("End time must be later than the start time.", "error")
        return redirect("/")

    # Name and Work ID come from the session, never from the form, so nobody can fake them.
    create_request(
        name=current_user.name,
        work_id=current_user.work_id,
        request_type=request_type,
        items_needed=items,
        date=date,
        time=time,
        end_time=end_time,
        venue=venue if request_type == "field_day" else "N/A",
    )
    flash("Request submitted successfully.", "success")
    return redirect("/")


@staff_bp.route("/my-requests")
@login_required
def my_requests():
    """The logged-in staff member's own request history."""
    if current_user.role == "admin":
        return redirect("/admin")
    return render_template("staff/my_requests.html", requests=get_requests_by_user(current_user.work_id))
