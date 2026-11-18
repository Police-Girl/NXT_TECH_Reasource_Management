# Importing necessary libraries and loading environment variables for Cosmos DB connection.
from azure.cosmos import CosmosClient
from dotenv import load_dotenv
import os

load_dotenv(dotenv_path=".env")

# Reading Cosmos DB credentials from environment variables
COSMOS_CONNECTION_STRING = os.getenv("COSMOS_CONNECTION_STRING")
COSMOS_DATABASE = os.getenv("COSMOS_DATABASE")

# Establishing connection to Cosmos DB and getting the database client
client = CosmosClient.from_connection_string(COSMOS_CONNECTION_STRING)
database = client.get_database_client(COSMOS_DATABASE)

# Dedicated container clients for easy import across your project
users_container = database.get_container_client("users")
requests_container = database.get_container_client("requests")
inventory_container = database.get_container_client("inventory")

# Dynamic helper function to fetch any container by name (defaults to 'requests')
def get_container(container_name='requests'):
    """Returns the requested Cosmos DB container client."""
    if container_name == 'users':
        return users_container
    elif container_name == 'inventory':
        return inventory_container
    return requests_container