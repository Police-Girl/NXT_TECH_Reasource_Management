# models/user_model.py - MODEL for users.
# Only talks to the database. It knows nothing about HTTP or HTML.

import uuid

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from db import get_container


class User(UserMixin):
    """The logged-in user object Flask-Login keeps in the session."""

    def __init__(self, data):
        self.id = data["id"]
        self.name = data["name"]
        self.work_id = data["work_id"]
        self.role = data["role"]
        self.email = data.get("email", "")


def _find(field, value):
    """Look up user documents where `field` equals `value` (parameterised query)."""
    return list(get_container("users").query_items(
        query=f"SELECT * FROM c WHERE c.{field} = @value",
        parameters=[{"name": "@value", "value": value}],
        enable_cross_partition_query=True,
    ))


def get_user_by_id(user_id):
    """Used by Flask-Login to reload the user from the session."""
    rows = _find("id", user_id)
    return User(rows[0]) if rows else None


def get_user_by_work_id(work_id):
    """Return the raw user document (a dict) or None."""
    rows = _find("work_id", work_id)
    return rows[0] if rows else None


def create_user(name, work_id, email, password, role="staff"):
    """Hash the password and save the user. Returns False if the work ID is taken."""
    if get_user_by_work_id(work_id):
        return False
    get_container("users").create_item(body={
        "id": str(uuid.uuid4()),
        "name": name,
        "work_id": work_id,
        "email": email,
        "password": generate_password_hash(password),  # never store plain text
        "role": role,
    })
    return True


def verify_password(user_data, password):
    """Compare a typed password with the stored hash."""
    return check_password_hash(user_data["password"], password)
