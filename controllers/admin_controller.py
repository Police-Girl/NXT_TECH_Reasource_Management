# controllers/admin_controller.py - CONTROLLER for everything admin-only.

import os
from datetime import datetime, timezone
from functools import wraps

from azure.cosmos import CosmosClient
from azure.cosmos.exceptions import CosmosResourceExistsError
from azure.identity import DefaultAzureCredential
from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from models.inventory_model import (
    CATEGORIES,
    create_inventory_item,
    delete_inventory_item,
    get_all_inventory,
    update_inventory_quantity,
)
from models.notification_model import create_notification
from models.request_model import (
    find_conflicts,
    get_all_requests,
    get_item_counts,
    get_request,
    get_type_counts,
    set_request_status,
)

# Blueprint grouping all administrative routes for the portal
admin_bp = Blueprint("admin", __name__)

# Azure Cosmos DB configuration read from environment variables;
# connects to the 'ntl-db' database and 'users' container for staff management.
COSMOS_ENDPOINT = os.environ.get("COSMOS_ENDPOINT", "")
COSMOS_DATABASE_NAME = os.environ.get("COSMOS_DATABASE", "ntl-db")
USERS_CONTAINER_NAME = os.environ.get("COSMOS_USERS_CONTAINER", "users")

# Cached CosmosClient authenticated with Microsoft Entra ID via DefaultAzureCredential
# (uses active Azure CLI credentials locally or a managed identity on Azure).
_cosmos_client = None


def _get_users_container():
    """Authenticate to Azure Cosmos DB and return the 'users' container client."""
    global _cosmos_client
    if _cosmos_client is None:
        if not COSMOS_ENDPOINT:
            raise RuntimeError("COSMOS_ENDPOINT environment variable is not set.")
        # DefaultAzureCredential resolves Entra ID tokens automatically without account keys
        _cosmos_client = CosmosClient(url=COSMOS_ENDPOINT, credential=DefaultAzureCredential())
    # Traverse the Azure Cosmos DB hierarchy: Account -> Database ('ntl-db') -> Container ('users')
    db = _cosmos_client.get_database_client(COSMOS_DATABASE_NAME)
    return db.get_container_client(USERS_CONTAINER_NAME)


def _list_staff_users() -> list[dict]:
    """Collect staff documents from Azure Cosmos DB and return them sorted newest-first."""
    container = _get_users_container()
    # Cross-partition query across the 'users' container to collect all documents with role == 'staff'.
    # Sorting is performed in Python rather than SQL ORDER BY so items missing 'created_at' still load.
    query = "SELECT * FROM c WHERE c.role = 'staff'"
    items = list(container.query_items(query=query, enable_cross_partition_query=True))
    return sorted(items, key=lambda u: u.get("created_at") or "", reverse=True)


def _staff_exists(container, work_id: str) -> bool:
    """Check Azure Cosmos DB for an existing account matching the normalized work_id."""
    # Parameterized query safely binds @work_id and scans across partitions in 'users'
    query = "SELECT VALUE COUNT(1) FROM c WHERE c.work_id = @work_id"
    params = [{"name": "@work_id", "value": work_id}]
    result = list(container.query_items(query=query, parameters=params, enable_cross_partition_query=True))
    return bool(result and result[0] > 0)


def admin_required(view):
    """Restrict route access to authenticated users with the 'admin' role."""
    @wraps(view)
    def wrapper(*args, **kwargs):
        if getattr(current_user, "role", None) != "admin":
            flash("Access denied.", "error")
            return redirect("/")
        return view(*args, **kwargs)
    return wrapper


# ---------------------------------------------------------------- dashboard
@admin_bp.route("/admin")
@login_required
@admin_required
def dashboard():
    """Render admin stats, charts, and request rows; supports optional status filtering."""
    all_requests = get_all_requests()
    status = request.args.get("filter")
    if status in ("pending", "approved", "rejected"):
        table_requests = [r for r in all_requests if r.get("status") == status]
    else:
        table_requests = all_requests

    return render_template(
        "admin/dashboard.html",
        requests=all_requests,          # full dataset powering top summary cards
        table_requests=table_requests,  # filtered or full dataset for the requests table
        type_counts=get_type_counts(all_requests),
        item_counts=get_item_counts(all_requests),
    )


# ---------------------------------------------------------------- approve / reject
def _notify_staff(item, status):
    """Create an in-platform notification in Cosmos DB for the requesting staff member."""
    req_label = (item.get("request_type") or "resource").replace("_", " ")
    create_notification(
        recipient_role="staff",
        message=(
            f"Your {req_label} request ({item.get('items_needed', '')}) "
            f"for {item.get('date', '')} was {status}."
        ),
        target_work_id=item["work_id"],
        link="/my-requests",
    )


@admin_bp.route("/admin/approve/<request_id>/<request_type>")
@login_required
@admin_required
def approve(request_id, request_type):
    """Approve a pending request after checking for overlapping resource bookings."""
    try:
        item = get_request(request_id, request_type)
    except Exception:
        flash("Request not found.", "error")
        return redirect("/admin")

    if item.get("status") != "pending":
        flash("That request has already been actioned.", "error")
        return redirect("/admin")

    # Block approval if another booking overlaps on the same date, time window, and item(s)
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
    _notify_staff(item, "approved")
    flash("Request approved and staff notified on the platform.", "success")
    return redirect("/admin")


@admin_bp.route("/admin/reject/<request_id>/<request_type>")
@login_required
@admin_required
def reject(request_id, request_type):
    """Reject a pending request and notify the staff member in-app."""
    try:
        item = get_request(request_id, request_type)
    except Exception:
        flash("Request not found.", "error")
        return redirect("/admin")

    if item.get("status") != "pending":
        flash("That request has already been actioned.", "error")
        return redirect("/admin")

    set_request_status(item, "rejected")
    _notify_staff(item, "rejected")
    flash("Request rejected and staff notified on the platform.", "success")
    return redirect("/admin")


# ---------------------------------------------------------------- inventory
@admin_bp.route("/admin/inventory")
@login_required
@admin_required
def inventory():
    """Render the read-only inventory overview page."""
    return render_template("admin/inventory.html", items=get_all_inventory())


@admin_bp.route("/admin/inventory/data")
@login_required
@admin_required
def inventory_data():
    """Return inventory items as JSON for live dashboard stock cards."""
    return jsonify(get_all_inventory())


@admin_bp.route("/admin/inventory/edit", methods=["GET", "POST"])
@login_required
@admin_required
def inventory_edit():
    """Display the inventory editor on GET or add a new inventory item on POST."""
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
    """Update the quantity of an existing item in the Cosmos DB inventory container."""
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
    """Delete an inventory item from its partition in Cosmos DB."""
    try:
        delete_inventory_item(item_id, category)
        flash("Item removed from inventory.", "success")
    except Exception:
        flash("Could not delete that item.", "error")
    return redirect("/admin/inventory/edit")


# ---------------------------------------------------------------- staff users
@admin_bp.route("/admin/users")
@login_required
@admin_required
def users():
    """Load existing staff accounts from Azure Cosmos DB and render the staff management view."""
    try:
        # Collect staff records for display in the staff directory table
        staff_list = _list_staff_users()
    except Exception as exc:
        print(f"[admin.users] Failed to load staff accounts: {exc}")
        staff_list = []
        flash("Could not load staff accounts from Cosmos DB.", "error")
    return render_template("admin/create_staff.html", staff_list=staff_list)


@admin_bp.route("/admin/users/create", methods=["POST"])
@login_required
@admin_required
def create_staff():
    """Validate submitted fields, prevent duplicate work IDs, and store a new staff user on Azure."""
    # Normalize incoming form fields before validation and persistence
    work_id = (request.form.get("work_id") or "").strip().upper()
    name = (request.form.get("name") or "").strip()
    email = (request.form.get("email") or "").strip().lower()
    department = (request.form.get("department") or "").strip()

    if not work_id or not name:
        flash("Work ID and full name are required.", "error")
        return redirect(url_for("admin.users"))

    try:
        container = _get_users_container()
        # Reject duplicate staff accounts before writing a new item
        if _staff_exists(container, work_id):
            flash(f"Staff account '{work_id}' already exists.", "error")
            return redirect(url_for("admin.users"))

        # Construct the JSON document persisted into the Azure 'users' container
        staff_doc = {
            "id": work_id,
            "work_id": work_id,
            "name": name,
            "email": email,
            "department": department,
            "role": "staff",
            "is_active": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created_by": getattr(current_user, "work_id", "ADMIN"),
        }
        # Insert the new document into Azure Cosmos DB
        container.create_item(body=staff_doc)
        flash(f"Created staff account for {name} ({work_id}).", "success")
    except CosmosResourceExistsError:
        # Guard against race conditions where an item with the same id/partition already exists
        flash(f"Staff account '{work_id}' already exists.", "error")
    except Exception as exc:
        flash(f"Error creating staff account: {exc}", "error")

    return redirect(url_for("admin.users"))