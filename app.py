# Importing Flask components (renaming request to avoid collisions with HTTP/Session objects)
from flask import Flask, render_template, request as flask_request, redirect, flash
# Import uuid for generating unique IDs for each request
import uuid
# Importing the get_container function to interact with Cosmos DB containers modularly
from db import get_container
# Importing the load_dotenv to read variables from the .env file
from dotenv import load_dotenv
# Importing the os to access environment variables
import os
# Flask-Login manages user sessions and authentication state
from flask_login import LoginManager, login_required, current_user
# Import the auth blueprint and User model
from auth import auth, User
# Import the send_notification function to send automated email updates
from mailer import send_notification

# Load the .env file so os.getenv() can read from it
load_dotenv()

# Read our Cosmos DB credentials from the .env file
COSMOS_CONNECTION_STRING = os.getenv("COSMOS_CONNECTION_STRING")
COSMOS_DATABASE = os.getenv("COSMOS_DATABASE")
COSMOS_CONTAINER = os.getenv("COSMOS_CONTAINER")

# Create the Flask app instance
app = Flask(__name__)
app.secret_key = "ntl-resource-secret"

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)

# If someone tries to access a protected page without logging in, send them to landing
login_manager.login_view = 'landing'

# Flask-Login calls this to reload the user from the session using the 'users' container
@login_manager.user_loader
def load_user(user_id):
    container = get_container('users')
    users = list(container.query_items(
        query=f"SELECT * FROM c WHERE c.id = '{user_id}'",
        enable_cross_partition_query=True
    ))
    if users:
        return User(users[0])
    return None

# Register the auth blueprint with the app
app.register_blueprint(auth)

# Landing page - shown to unauthenticated users
@app.route("/landing")
def landing():
    if current_user.is_authenticated:
        return redirect("/admin" if current_user.role == 'admin' else "/")
    return render_template("landing.html")

# Home route - fetches inventory from Cosmos DB and passes it to index.html for the dropdown
@app.route("/")
def home():
    if current_user.is_authenticated:
        if current_user.role == 'admin':
            return redirect("/admin")
        
        # Query inventory container from Cosmos DB to populate the request dropdown
        inv_container = get_container('inventory')
        inventory_items = list(inv_container.query_items(
            query="SELECT * FROM c ORDER BY c.name ASC",
            enable_cross_partition_query=True
        ))
        return render_template("index.html", inventory=inventory_items)
        
    return redirect("/landing")

# Staff request form page - alternative route fetching inventory for dropdown
@app.route("/staff/request", methods=["GET"])
@login_required
def staff_request_page():
    if current_user.role == 'admin':
        flash("Admins cannot submit requests.", "error")
        return redirect("/admin")
    
    inv_container = get_container('inventory')
    inventory_items = list(inv_container.query_items(
        query="SELECT * FROM c ORDER BY c.name ASC",
        enable_cross_partition_query=True
    ))
    
    return render_template("staff_request.html", inventory=inventory_items)

# Submit route - saves a new request to Cosmos DB (Staff role only)
@app.route("/submit", methods=["POST"])
@login_required
def submit():
    if current_user.role == 'admin':
        flash("Admins cannot submit requests.", "error")
        return redirect("/admin")
        
    data = {
        "id": str(uuid.uuid4()),
        "name": flask_request.form.get("name"),
        "work_id": flask_request.form.get("work_id"),
        "request_type": flask_request.form.get("request_type"),
        "items_needed": flask_request.form.get("items_needed"),
        "quantity_needed": int(flask_request.form.get("quantity_needed", 1)),
        "date": flask_request.form.get("date"),
        "time": flask_request.form.get("time"),
        "end_time": flask_request.form.get("end_time"),
        "venue": flask_request.form.get("venue", "N/A"),
        "status": "pending"
    }
    container = get_container('requests')
    container.create_item(body=data)
    flash("Request submitted successfully!", "success")
    return redirect("/")

# My requests page - shows only the logged-in user's requests (Staff role only)
@app.route("/my-requests")
@login_required
def my_requests():
    if current_user.role == 'admin':
        return redirect("/admin")
    container = get_container('requests')
    items = list(container.query_items(
        query=f"SELECT * FROM c WHERE c.work_id = '{current_user.work_id}' ORDER BY c._ts DESC",
        enable_cross_partition_query=True
    ))
    return render_template("my_requests.html", requests=items)

# Admin dashboard - fetches all requests and inventory from Cosmos DB and displays them
@app.route("/admin")
@login_required
def admin():
    if current_user.role != 'admin':
        flash("Access denied.", "error")
        return redirect("/")
    
    container = get_container('requests')
    requests_items = list(container.query_items(
        query="SELECT * FROM c ORDER BY c._ts DESC",
        enable_cross_partition_query=True
    ))
    
    inv_container = get_container('inventory')
    inventory_items = list(inv_container.query_items(
        query="SELECT * FROM c ORDER BY c.name ASC",
        enable_cross_partition_query=True
    ))
    
    return render_template("admin.html", requests=requests_items, inventory=inventory_items)

# Approve a request - updates status, performs automated inventory deduction, and emails staff
@app.route("/admin/approve/<id>/<request_type>")
@login_required
def approve(id, request_type):
    if current_user.role != 'admin':
        return redirect("/")
    
    container = get_container('requests')
    item = container.read_item(item=id, partition_key=request_type)
    item["status"] = "approved"
    container.upsert_item(body=item)
    
    # --- AUTOMATIC INVENTORY DEDUCTION ---
    try:
        inv_container = get_container('inventory')
        target_name = item.get('items_needed', '').strip()
        
        # Case-insensitive query to match inventory item names securely
        inv_items = list(inv_container.query_items(
            query=f"SELECT * FROM c WHERE LOWER(c.name) = LOWER('{target_name}')",
            enable_cross_partition_query=True
        ))
        
        if inv_items:
            inv_item = inv_items[0]
            try:
                qty_to_deduct = int(item.get('quantity_needed', 1))
            except ValueError:
                qty_to_deduct = 1
                
            # Safely deduct stock ensuring quantity never drops below zero
            inv_item['quantity'] = max(0, inv_item['quantity'] - qty_to_deduct)
            
            # Use upsert_item to safely update the record in Cosmos DB
            inv_container.upsert_item(body=inv_item)
    except Exception as e:
        print(f"Error updating inventory: {e}")
    # -------------------------------------

    # Fetch user email to dispatch notification
    user_container = get_container('users')
    users = list(user_container.query_items(
        query=f"SELECT * FROM c WHERE c.work_id = '{item['work_id']}'",
        enable_cross_partition_query=True
    ))
    if users and users[0].get('email'):
        send_notification(users[0]['email'], item['name'], item.get('items_needed', item['request_type']), 'approved')
        
    flash("Request approved and inventory updated!", "success")
    return redirect("/admin")

# Reject a request - updates status in Cosmos DB and notifies staff
@app.route("/admin/reject/<id>/<request_type>")
@login_required
def reject(id, request_type):
    if current_user.role != 'admin':
        return redirect("/")
        
    container = get_container('requests')
    item = container.read_item(item=id, partition_key=request_type)
    item["status"] = "rejected"
    container.upsert_item(body=item)
    
    user_container = get_container('users')
    users = list(user_container.query_items(
        query=f"SELECT * FROM c WHERE c.work_id = '{item['work_id']}'",
        enable_cross_partition_query=True
    ))
    if users and users[0].get('email'):
        send_notification(users[0]['email'], item['name'], item.get('items_needed', item['request_type']), 'rejected')
        
    flash("Request rejected.", "error")
    return redirect("/admin")

# Route for admins to view the inventory list from Cosmos DB
@app.route("/admin/inventory")
@login_required
def view_inventory():
    if current_user.role != 'admin':
        flash("Access denied.", "error")
        return redirect("/")
    inv_container = get_container('inventory')
    items = list(inv_container.query_items(
        query="SELECT * FROM c ORDER BY c.name ASC",
        enable_cross_partition_query=True
    ))
    return render_template("view_inventory.html", inventory=items)

# Route for viewing, modifying quantities, and adding new inventory items in Cosmos DB
@app.route("/admin/inventory/edit", methods=["GET", "POST"])
@login_required
def edit_inventory():
    if current_user.role != 'admin':
        flash("Access denied.", "error")
        return redirect("/")
    
    container = get_container('inventory')
    
    if flask_request.method == "POST":
        action = flask_request.form.get("action")
        
        # Handle adding a brand new item/category to Cosmos DB
        if action == "add":
            name = flask_request.form.get("name")
            quantity = int(flask_request.form.get("quantity", 0))
            new_item = {
                "id": str(uuid.uuid4()),
                "name": name,
                "quantity": quantity
            }
            container.create_item(body=new_item)
            flash("New item category added successfully to database!", "success")
            
        # Handle updating quantities for existing items in Cosmos DB
        elif action == "update":
            item_id = flask_request.form.get("id")
            new_qty = int(flask_request.form.get("quantity", 0))
            
            items = list(container.query_items(
                query=f"SELECT * FROM c WHERE c.id = '{item_id}'",
                enable_cross_partition_query=True
            ))
            if items:
                item = items[0]
                item["quantity"] = new_qty
                container.upsert_item(body=item)
                flash("Inventory updated successfully!", "success")
            
        return redirect("/admin/inventory/edit")
        
    items = list(container.query_items(
        query="SELECT * FROM c ORDER BY c.name ASC",
        enable_cross_partition_query=True
    ))
    return render_template("edit_inventory.html", inventory=items)

# Run the Flask development server when this file is executed directly
if __name__ == "__main__":
    app.run(debug=True)