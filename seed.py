# seed.py - Idempotent database seeder for users, inventory, and requests.
# Run with: python seed.py

from db import get_container
from models.inventory_model import CATEGORIES, create_inventory_item, get_all_inventory
from models.request_model import create_request, set_request_status
from models.user_model import create_user, get_user_by_work_id

# 1. Default Users (Admin + Staff)
SEED_USERS = [
    {
        "name": "Nicole Admin",
        "work_id": "ADMIN-01",
        "email": "admin@nxttech.local",
        "password": "AdminPassword123!",
        "role": "admin",
    },
    {
        "name": "Brian Staff",
        "work_id": "STAFF-01",
        "email": "brian@nxttech.local",
        "password": "StaffPassword123!",
        "role": "staff",
    },
    {
        "name": "Jane Staff",
        "work_id": "STAFF-02",
        "email": "jane@nxttech.local",
        "password": "StaffPassword123!",
        "role": "staff",
    },
]

# 2. Sample Inventory across CATEGORIES (partition key: /category)
SEED_INVENTORY = [
    {"name": "Dell Latitude 5540 Laptop", "category": "Equipment", "quantity": 12},
    {"name": "Epson EB-X49 Projector", "category": "Equipment", "quantity": 4},
    {"name": "Toyota Hilux Double Cab", "category": "Vehicles", "quantity": 3},
    {"name": "Nissan NV350 Van", "category": "Vehicles", "quantity": 2},
    {"name": "Ergonomic Mesh Office Chair", "category": "Furniture", "quantity": 20},
    {"name": "Foldable Conference Table", "category": "Furniture", "quantity": 6},
    {"name": "Nespresso Commercial Coffee Machine", "category": "Appliances", "quantity": 3},
    {"name": "Standing Water Dispenser", "category": "Appliances", "quantity": 5},
    {"name": "Buffet Chafing Dish Set", "category": "Catering", "quantity": 10},
    {"name": "Insulated Beverage Urn (20L)", "category": "Catering", "quantity": 4},
    {"name": "USB-C Multiport Hub", "category": "Accessories", "quantity": 15},
    {"name": "Wireless Presentation Clicker", "category": "Accessories", "quantity": 8},
]

# 3. Sample Requests matched to request_model.py (partition key: /request_type)
SEED_REQUESTS = [
    {
        "name": "Brian Staff",
        "work_id": "STAFF-01",
        "request_type": "office_items",
        "items_needed": "Dell Latitude 5540 Laptop, USB-C Multiport Hub",
        "date": "2026-11-25",
        "time": "09:00",
        "end_time": "12:00",
        "venue": "Boardroom A",
        "status": "pending",
    },
    {
        "name": "Jane Staff",
        "work_id": "STAFF-02",
        "request_type": "field_day",
        "items_needed": "Toyota Hilux Double Cab, Epson EB-X49 Projector",
        "date": "2026-11-26",
        "time": "08:00",
        "end_time": "16:00",
        "venue": "Client Site - Westlands",
        "status": "approved",
    },
    {
        "name": "Brian Staff",
        "work_id": "STAFF-01",
        "request_type": "catering",
        "items_needed": "Buffet Chafing Dish Set, Insulated Beverage Urn (20L)",
        "date": "2026-11-27",
        "time": "12:00",
        "end_time": "14:00",
        "venue": "Main Conference Hall",
        "status": "rejected",
    },
]


def seed_users():
    print("--- Seeding users ---")
    for u in SEED_USERS:
        if get_user_by_work_id(u["work_id"]):
            print(f"  [SKIP] User {u['work_id']} already exists.")
            continue
        created = create_user(
            name=u["name"],
            work_id=u["work_id"],
            email=u["email"],
            password=u["password"],
            role=u["role"],
        )
        if created:
            print(f"  [ADDED] {u['role'].upper()}: {u['work_id']} ({u['name']})")
        else:
            print(f"  [WARN] Could not create {u['work_id']}.")


def seed_inventory():
    print("--- Seeding inventory ---")
    existing_items = get_all_inventory()
    existing_keys = {(item.get("name"), item.get("category")) for item in existing_items}

    for item in SEED_INVENTORY:
        if item["category"] not in CATEGORIES:
            print(f"  [WARN] Invalid category '{item['category']}', skipping.")
            continue
        if (item["name"], item["category"]) in existing_keys:
            print(f"  [SKIP] '{item['name']}' ({item['category']}) already exists.")
            continue
        create_inventory_item(
            name=item["name"],
            category=item["category"],
            quantity=item["quantity"],
        )
        print(f"  [ADDED] {item['name']} ({item['category']}) x{item['quantity']}")


def seed_requests():
    print("--- Seeding requests ---")
    container = get_container("requests")
    existing = list(container.query_items(
        query="SELECT TOP 1 * FROM c",
        enable_cross_partition_query=True,
    ))
    if existing:
        print("  [SKIP] 'requests' container already has data.")
        return

    for req in SEED_REQUESTS:
        created = create_request(
            name=req["name"],
            work_id=req["work_id"],
            request_type=req["request_type"],
            items_needed=req["items_needed"],
            date=req["date"],
            time=req["time"],
            end_time=req["end_time"],
            venue=req["venue"],
        )
        if req["status"] != "pending":
            set_request_status(created, req["status"])
        print(f"  [ADDED] Request by {req['work_id']} ({req['request_type']} - {req['status']})")


if __name__ == "__main__":
    seed_users()
    seed_inventory()
    seed_requests()
    print("\nDatabase seeding complete.")