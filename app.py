# app.py - Entry point. Builds the Flask app and plugs the controllers in.
# No route logic lives here except the public landing page.

from pathlib import Path
import os

from dotenv import load_dotenv
from flask import Flask, redirect, render_template, request
from flask_login import LoginManager, current_user, login_required

load_dotenv(Path(__file__).resolve().parent / ".env")

from controllers.admin_controller import admin_bp
from controllers.auth_controller import auth_bp
from controllers.staff_controller import staff_bp
from models.notification_model import get_notifications_for_user, mark_notification_read
from models.user_model import get_user_by_id

app = Flask(__name__, template_folder="views")
app.secret_key = os.getenv("SECRET_KEY", "change-me-in-env")

# Flask-Login: anyone not signed in is sent to the landing page
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "landing"
login_manager.login_message = None


@login_manager.user_loader
def load_user(user_id):
    return get_user_by_id(user_id)


@app.context_processor
def inject_notifications():
    """Make in-app platform notifications available across views for signed-in users."""
    if current_user.is_authenticated:
        items = get_notifications_for_user(current_user.role, current_user.work_id)
        unread = sum(1 for n in items if not n.get("is_read"))
        return {"nav_notifications": items, "unread_notifications_count": unread}
    return {"nav_notifications": [], "unread_notifications_count": 0}


@app.route("/notifications/read/<notif_id>", methods=["POST"])
@login_required
def read_notification(notif_id):
    mark_notification_read(notif_id, current_user.role)
    return redirect(request.referrer or ("/admin" if current_user.role == "admin" else "/"))


# Register the three controllers
app.register_blueprint(auth_bp)
app.register_blueprint(staff_bp)
app.register_blueprint(admin_bp)


@app.route("/landing")
def landing():
    """Public page with the staff and admin sign-in cards."""
    return render_template("landing.html")


if __name__ == "__main__":
    app.run(debug=True)