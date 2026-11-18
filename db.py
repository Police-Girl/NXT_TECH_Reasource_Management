# db.py - Database connection layer.
# The only file that knows HOW to reach Azure Cosmos DB. Models call get_container().

from pathlib import Path
import os

from azure.cosmos import CosmosClient
from dotenv import load_dotenv

# Load .env from the project root, no matter which folder the app is started from
load_dotenv(Path(__file__).resolve().parent / ".env")

_client = None
_database = None


def _get_database():
    """Connect to Cosmos DB the first time it is needed, then reuse the connection."""
    global _client, _database
    if _database is None:
        connection_string = os.getenv("COSMOS_CONNECTION_STRING")
        if not connection_string:
            raise RuntimeError("COSMOS_CONNECTION_STRING is missing from .env")
        _client = CosmosClient.from_connection_string(connection_string)
        _database = _client.get_database_client(os.getenv("COSMOS_DATABASE", "ntl-db"))
    return _database


def get_container(name="requests"):
    """Return a container client: 'requests', 'users' or 'inventory'."""
    return _get_database().get_container_client(name)
