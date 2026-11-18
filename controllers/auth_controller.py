# controllers/auth_controller.py - CONTROLLER for register / login / logout.
# Receives the HTTP request, asks the model to do the data work, returns a view.

from flask import Blueprint, flash, redirect, render_template, request
from flask_login import login_required, login_user, logout_user

from models.user_model import User, create_user, get_user_by_work_id, verify_password

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    """GET shows the form. POST creates a STAFF account (admins are created by IT)."""
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        work_id = request.form.get("work_id", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")

        if not (name and work_id and email and password):
            flash("Please fill in every field.", "error")
            return redirect("/register")
        if password != confirm:
            flash("Passwords do not match.", "error")
            return redirect("/register")

        # Role is forced to 'staff' here - nobody can self-register as admin.
        if not create_user(name, work_id, email, password, role="staff"):
            flash("That Work ID is already registered.", "error")
            return redirect("/register")

        flash("Account created. Please sign in.", "success")
        return redirect("/landing")

    return render_template("register.html")


@auth_bp.route("/login", methods=["POST"])
def login():
    """Checks credentials, starts the session, sends each role to its own home page."""
    work_id = request.form.get("work_id", "").strip()
    password = request.form.get("password", "")
    portal = request.form.get("role", "staff")  # which card they used on the landing page

    user_data = get_user_by_work_id(work_id)
    if not user_data or not verify_password(user_data, password):
        flash("Invalid Work ID or password.", "error")
        return redirect("/landing")

    if user_data["role"] != portal:
        flash(f"This account is not a {portal} account.", "error")
        return redirect("/landing")

    user = User(user_data)
    login_user(user)
    flash(f"Welcome, {user.name}.", "success")
    return redirect("/admin" if user.role == "admin" else "/")


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Signed out successfully.", "success")
    return redirect("/landing")
