# models/notification_model.py - MODEL for cross-platform in-app notifications.
# Uses Cosmos DB container 'notifications' with partition key '/recipient_role'
# (or '/target_key'—here we partition by '/recipient_role': 'admin' or 'staff').

from datetime import datetime, timezone
import uuid

from azure.cosmos.exceptions import CosmosResourceNotFoundError
from db import get_container


def _container():
    return get_container("notifications")


def create_notification(recipient_role, message, target_work_id=None, link="/"):
    """Create a notification for 'admin' (all admins) or a specific 'staff' work_id."""
    doc = {
        "id": str(uuid.uuid4()),
        "recipient_role": recipient_role,  # "admin" or "staff" (partition key: /recipient_role)
        "target_work_id": target_work_id,  # None for admin broadcasts, or staff work_id for targeted staff alerts
        "message": message,
        "link": link,
        "is_read": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        _container().create_item(body=doc)
    except CosmosResourceNotFoundError:
        # Container not created yet; avoid crashing core request flow
        return None
    return doc


def get_notifications_for_user(role, work_id, limit=20):
    """Return recent notifications for an admin or a specific staff member."""
    try:
        if role == "admin":
            items = list(_container().query_items(
                query="SELECT * FROM c WHERE c.recipient_role = 'admin' ORDER BY c.created_at DESC OFFSET 0 LIMIT @limit",
                parameters=[{"name": "@limit", "value": limit}],
                partition_key="admin",
            ))
        else:
            items = list(_container().query_items(
                query="SELECT * FROM c WHERE c.recipient_role = 'staff' AND c.target_work_id = @work_id ORDER BY c.created_at DESC OFFSET 0 LIMIT @limit",
                parameters=[
                    {"name": "@work_id", "value": work_id},
                    {"name": "@limit", "value": limit},
                ],
                partition_key="staff",
            ))
        return items
    except CosmosResourceNotFoundError:
        return []


def mark_notification_read(notif_id, recipient_role):
    """Mark a single notification as read."""
    try:
        container = _container()
        doc = container.read_item(item=notif_id, partition_key=recipient_role)
        doc["is_read"] = True
        container.replace_item(item=notif_id, body=doc)
        return True
    except CosmosResourceNotFoundError:
        return False