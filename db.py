#Importing necessary libraries and loading environment variables for Cosmos DB connection.
from azure.cosmos import CosmosClient

from dotenv import load_dotenv

import os

load_dotenv(dotenv_path=".env")
# Reading Cosmos DB credentials from environment variables
COSMOS_CONNECTION_STRING = os.getenv("COSMOS_CONNECTION_STRING")
COSMOS_DATABASE = os.getenv("COSMOS_DATABASE")
COSMOS_CONTAINER = os.getenv("COSMOS_CONTAINER")
# Establishing connection to Cosmos DB and getting the container client
client = CosmosClient.from_connection_string(COSMOS_CONNECTION_STRING)
database = client.get_database_client(COSMOS_DATABASE)
container = database.get_container_client(COSMOS_CONTAINER)

# Function to get the Cosmos DB container client
def get_container():
    return container