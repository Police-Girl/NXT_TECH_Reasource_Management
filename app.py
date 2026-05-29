# Importing the Flask and render_template for routing and serving HTML pages
from flask import Flask, render_template, request, redirect, flash
#Import uuid for generating unique IDs for each request
import uuid
# Importing the get_container function to interact with Cosmos DB
from db import get_container
# Importing the  load_dotenv to read variables from the .env file
from dotenv import load_dotenv
# Importing the  os to access environment variables
import os

# Load the .env file so os.getenv() can read from it
load_dotenv()
# Read our Cosmos DB credentials from the .env file
COSMOS_CONNECTION_STRING = os.getenv("COSMOS_CONNECTION_STRING")
COSMOS_DATABASE = os.getenv("COSMOS_DATABASE")
COSMOS_CONTAINER = os.getenv("COSMOS_CONTAINER")
# Create the Flask app instance
app = Flask(__name__)
app.secret_key = "ntl-resource-secret"
# Define the home route - when someone visits "/", run this function
@app.route("/")
def index():
    return render_template("index.html")
# Define the route to render the index.html page with data from Cosmos DB
@app.route("/submit", methods=["POST"])
def submit():
    # Get form data
    data = {
        "id": str(uuid.uuid4()),
        "name": request.form.get("name"),
        "work_id": request.form.get("work_id"),
        "request_type": request.form.get("request_type"),
        "items_needed": request.form.get("items_needed"),
        "date": request.form.get("date"),
        "time": request.form.get("time"),
        "venue": request.form.get("venue", "N/A"),
        "status": "pending"
    }
    
    # Save to Cosmos DB
    container = get_container()
    container.create_item(body=data)
    
    flash("Request submitted successfully!", "success")
    return redirect("/")

    # Admin dashboard - fetch all requests from Cosmos DB and display them
@app.route("/admin")
def admin():
    container = get_container()
    items = list(container.query_items(
        query="SELECT * FROM c ORDER BY c._ts DESC",
        enable_cross_partition_query=True
    ))
    return render_template("admin.html", requests=items)

# Approve a request - update its status in Cosmos DB
@app.route("/admin/approve/<id>/<request_type>")
def approve(id, request_type):
    container = get_container()
    item = container.read_item(item=id, partition_key=request_type)
    item["status"] = "approved"
    container.replace_item(item=id, body=item)
    flash("Request approved!", "success")
    return redirect("/admin")

# Reject a request - update its status in Cosmos DB
@app.route("/admin/reject/<id>/<request_type>")
def reject(id, request_type):
    container = get_container()
    item = container.read_item(item=id, partition_key=request_type)
    item["status"] = "rejected"
    container.replace_item(item=id, body=item)
    flash("Request rejected.", "error")
    return redirect("/admin")

#lets run only the flas server only if this script is run directly (not imported as a module)
if __name__ == "__main__":
    app.run(debug=True)