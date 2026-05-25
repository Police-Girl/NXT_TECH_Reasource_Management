# Importing the Flask and render_template for routing and serving HTML pages
from flask import Flask, render_template
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
# Define the home route - when someone visits "/", run this function
@app.route("/")
def index():
    return "Hello, world!"

# Run the app in debug mode when executing this file directly
if __name__ == "__main__":
    app.run(debug=True)