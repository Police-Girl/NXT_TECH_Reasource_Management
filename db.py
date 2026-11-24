# db.py - Database connection layer using Microsoft Entra ID.

from pathlib import Path
import os

from azure.cosmos import CosmosClient
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env", override=True)

_client = None
_database = None


def _extract_endpoint() -> str:
    """Get COSMOS_ENDPOINT directly or parse AccountEndpoint from COSMOS_CONNECTION_STRING."""
    endpoint = os.getenv("COSMOS_ENDPOINT", "").strip().strip('"').strip("'")
    if endpoint:
        return endpoint

    raw_conn = os.getenv("COSMOS_CONNECTION_STRING", "").strip().strip('"').strip("'")
    for segment in raw_conn.split(";"):
        if "=" in segment:
            key, val = segment.split("=", 1)
            if key.strip() == "AccountEndpoint":
                return val.strip()

    raise RuntimeError("Missing COSMOS_ENDPOINT or AccountEndpoint in .env")


def _get_database():
    """Connect to Cosmos DB once using Entra ID and reuse the database client."""
    global _client, _database
    if _database is None:
        endpoint = _extract_endpoint()
        credential = DefaultAzureCredential()
        _client = CosmosClient(url=endpoint, credential=credential)
        db_name = os.getenv("COSMOS_DATABASE", "ntl-db").strip().strip('"').strip("'")
        _database = _client.get_database_client(db_name)
    return _database


def get_container(name="requests"):
    """Return a container client: 'requests', 'users' or 'inventory'."""
    return _get_database().get_container_client(name)