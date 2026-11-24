import os
import uuid
from datetime import datetime, timezone
from azure.cosmos import CosmosClient
from azure.identity import DefaultAzureCredential
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user

# Blueprint for direct Staff <-> Admin messaging
message_bp = Blueprint("message_bp", __name__)

# Cosmos DB configuration (matches NTL resource portal setup)
COSMOS_ENDPOINT = os.environ.get("COSMOS_ENDPOINT", "")
COSMOS_DATABASE_NAME = os.environ.get("COSMOS_DATABASE", "ntl-db")
MESSAGES_CONTAINER_NAME = os.environ.get("COSMOS_MESSAGES_CONTAINER", "messages")
USERS_CONTAINER_NAME = os.environ.get("COSMOS_USERS_CONTAINER", "users")
NOTIFICATIONS_CONTAINER_NAME = os.environ.get("COSMOS_NOTIFICATIONS_CONTAINER", "notifications")

_cosmos_client = None


def _get_cosmos_client() -> CosmosClient:
    """Create and cache a CosmosClient authenticated via Entra ID (DefaultAzureCredential)."""
    global _cosmos_client
    if _cosmos_client is None:
        if not COSMOS_ENDPOINT:
            raise RuntimeError("COSMOS_ENDPOINT environment variable is not set.")
        credential = DefaultAzureCredential()
        _cosmos_client = CosmosClient(url=COSMOS_ENDPOINT, credential=credential)
    return _cosmos_client


def _get_container(container_name: str):
    """Return a container client from the 'ntl-db' database."""
    db = _get_cosmos_client().get_database_client(COSMOS_DATABASE_NAME)
    return db.get_container_client(container_name)


def _push_in_app_notification(recipient_role: str, message: str, recipient_work_id: str | None = None) -> None:
    """
    Write a pure in-platform notification into the 'notifications' container
    (partitioned by /recipient_role) so the navbar bell updates without email.
    """
    try:
        notif_container = _get_container(NOTIFICATIONS_CONTAINER_NAME)
        doc = {
            "id": str(uuid.uuid4()),
            "recipient_role": recipient_role,
            "recipient_work_id": recipient_work_id,
            "message": message,
            "is_read": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        notif_container.upsert_item(doc)
    except Exception:
        # Avoid blocking message delivery if notifications container is temporarily unavailable
        pass


def _fetch_staff_accounts() -> list[dict]:
    """Retrieve all staff users so Admin can start or continue a direct thread with any staff member."""
    try:
        users_container = _get_container(USERS_CONTAINER_NAME)
        query = "SELECT * FROM c WHERE c.role = 'staff'"
        return list(users_container.query_items(query=query, enable_cross_partition_query=True))
    except Exception:
        return []


def _fetch_thread_messages(thread_id: str) -> list[dict]:
    """Query all messages in a single direct thread using /thread_id as partition key."""
    msg_container = _get_container(MESSAGES_CONTAINER_NAME)
    query = "SELECT * FROM c WHERE c.thread_id = @thread_id ORDER BY c.created_at ASC"
    params = [{"name": "@thread_id", "value": thread_id}]
    return list(
        msg_container.query_items(
            query=query,
            parameters=params,
            partition_key=thread_id,
        )
    )


def _mark_incoming_as_read(messages: list[dict], incoming_role: str) -> None:
    """Mark unread messages sent by `incoming_role` as read in Cosmos DB."""
    if not messages:
        return
    msg_container = _get_container(MESSAGES_CONTAINER_NAME)
    for item in messages:
        if item.get("sender_role") == incoming_role and not item.get("is_read"):
            item["is_read"] = True
            msg_container.upsert_item(item)


def _build_admin_threads() -> list[dict]:
    """Group messages into per-staff threads for the Admin inbox."""
    msg_container = _get_container(MESSAGES_CONTAINER_NAME)
    all_messages = list(
        msg_container.query_items(
            query="SELECT * FROM c ORDER BY c.created_at ASC",
            enable_cross_partition_query=True,
        )
    )

    threads: dict[str, dict] = {}

    # Seed threads from known staff users so Admin can message any staff user proactively
    for staff in _fetch_staff_accounts():
        work_id = (staff.get("work_id") or "").strip()
        if not work_id:
            continue
        tid = f"staff_{work_id}"
        threads[tid] = {
            "thread_id": tid,
            "staff_work_id": work_id,
            "staff_name": staff.get("name") or work_id,
            "messages": [],
            "unread_count": 0,
            "last_message": "No messages yet",
            "last_time": "",
        }

    # Populate messages and count unread staff messages per thread
    for msg in all_messages:
        work_id = (msg.get("staff_work_id") or "unknown").strip()
        tid = msg.get("thread_id") or f"staff_{work_id}"
        if tid not in threads:
            threads[tid] = {
                "thread_id": tid,
                "staff_work_id": work_id,
                "staff_name": msg.get("staff_name") or work_id,
                "messages": [],
                "unread_count": 0,
                "last_message": "",
                "last_time": "",
            }

        threads[tid]["messages"].append(msg)
        threads[tid]["last_message"] = msg.get("body", "")
        threads[tid]["last_time"] = msg.get("created_at", "")

        if msg.get("sender_role") == "staff" and not msg.get("is_read"):
            threads[tid]["unread_count"] += 1

    # Show active conversations first, ordered by most recent message
    return sorted(
        threads.values(),
        key=lambda t: (bool(t["last_time"]), t["last_time"]),
        reverse=True,
    )


@message_bp.route("/messages", methods=["GET"])
@login_required
def inbox():
    """Render the Staff <-> Admin direct messaging inbox."""
    role = (getattr(current_user, "role", "staff") or "staff").lower()

    if role == "admin":
        threads = _build_admin_threads()
        selected_tid = request.args.get("thread_id")
        active_thread = (
            next((t for t in threads if t["thread_id"] == selected_tid), None)
            if selected_tid
            else (threads[0] if threads else None)
        )

        if active_thread:
            _mark_incoming_as_read(active_thread["messages"], incoming_role="staff")
            active_thread["unread_count"] = 0

        return render_template(
            "messages/inbox.html",
            is_admin=True,
            threads=threads,
            active_thread=active_thread,
        )

    # Staff member sees their single direct conversation with Admin
    staff_work_id = getattr(current_user, "work_id", "")
    thread_id = f"staff_{staff_work_id}"
    chat_messages = _fetch_thread_messages(thread_id)
    _mark_incoming_as_read(chat_messages, incoming_role="admin")

    return render_template(
        "messages/inbox.html",
        is_admin=False,
        chat_messages=chat_messages,
    )


@message_bp.route("/messages/send", methods=["POST"])
@login_required
def send():
    """Persist a new Staff <-> Admin message in Cosmos DB and trigger an in-app alert."""
    body = (request.form.get("body") or "").strip()
    if not body:
        flash("Please enter a message before sending.", "error")
        return redirect(url_for("message_bp.inbox"))

    role = (getattr(current_user, "role", "staff") or "staff").lower()
    now_iso = datetime.now(timezone.utc).isoformat()
    msg_container = _get_container(MESSAGES_CONTAINER_NAME)

    if role == "admin":
        target_work_id = (request.form.get("staff_work_id") or "").strip()
        target_staff_name = (request.form.get("staff_name") or target_work_id).strip()
        if not target_work_id:
            flash("Select a staff thread before sending a reply.", "error")
            return redirect(url_for("message_bp.inbox"))

        thread_id = f"staff_{target_work_id}"
        doc = {
            "id": str(uuid.uuid4()),
            "thread_id": thread_id,
            "staff_work_id": target_work_id,
            "staff_name": target_staff_name,
            "sender_work_id": getattr(current_user, "work_id", "ADMIN"),
            "sender_name": getattr(current_user, "name", "Admin"),
            "sender_role": "admin",
            "recipient_role": "staff",
            "recipient_work_id": target_work_id,
            "body": body,
            "created_at": now_iso,
            "is_read": False,
        }
        msg_container.upsert_item(doc)

        _push_in_app_notification(
            recipient_role="staff",
            recipient_work_id=target_work_id,
            message=f"Admin replied: {body[:75]}",
        )
        flash("Reply sent.", "success")
        return redirect(url_for("message_bp.inbox", thread_id=thread_id))

    # Staff user sending a direct message to Admin
    staff_work_id = getattr(current_user, "work_id", "")
    staff_name = getattr(current_user, "name", staff_work_id)
    thread_id = f"staff_{staff_work_id}"

    doc = {
        "id": str(uuid.uuid4()),
        "thread_id": thread_id,
        "staff_work_id": staff_work_id,
        "staff_name": staff_name,
        "sender_work_id": staff_work_id,
        "sender_name": staff_name,
        "sender_role": "staff",
        "recipient_role": "admin",
        "recipient_work_id": None,
        "body": body,
        "created_at": now_iso,
        "is_read": False,
    }
    msg_container.upsert_item(doc)

    _push_in_app_notification(
        recipient_role="admin",
        recipient_work_id=None,
        message=f"New message from {staff_name} ({staff_work_id}): {body[:75]}",
    )
    flash("Message sent to Admin.", "success")
    return redirect(url_for("message_bp.inbox"))