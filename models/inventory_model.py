# models/inventory_model.py - MODEL for inventory items.
# Container 'inventory', partition key /category.

import uuid

from db import get_container

CATEGORIES = ["Equipment", "Vehicles", "Furniture", "Appliances", "Catering", "Accessories"]


def get_all_inventory():
    """All inventory items, A-Z by name."""
    return list(get_container("inventory").query_items(
        query="SELECT * FROM c ORDER BY c.name ASC",
        enable_cross_partition_query=True,
    ))


def create_inventory_item(name, category, quantity):
    item = {
        "id": str(uuid.uuid4()),
        "name": name,
        "category": category,
        "quantity": max(0, int(quantity)),
    }
    get_container("inventory").create_item(body=item)
    return item


def update_inventory_quantity(item_id, category, quantity):
    container = get_container("inventory")
    item = container.read_item(item=item_id, partition_key=category)
    item["quantity"] = max(0, int(quantity))
    container.replace_item(item=item_id, body=item)
    return item


def delete_inventory_item(item_id, category):
    get_container("inventory").delete_item(item=item_id, partition_key=category)
