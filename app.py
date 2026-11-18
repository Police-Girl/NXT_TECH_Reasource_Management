# app.py - Entry point. Builds the Flask app and plugs the controllers in.
# No route logic lives here except the public landing page.

from pathlib import Path
import os

from dotenv import load_dotenv
from flask import Flask, render_template
from flask_login import LoginManager

load_dotenv(Path(__file__).resolve().parent / ".env")

from controllers.admin_controller import admin_bp
from controllers.auth_controller import auth_bp
from controllers.staff_controller import staff_bp
from models.user_model import get_user_by_id

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "change-me-in-env")

# Flask-Login: anyone not signed in is sent to the landing page
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "landing"
login_manager.login_message = None


@login_manager.user_loader
def load_user(user_id):
    return get_user_by_id(user_id)


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
