import os
from pathlib import Path
from dotenv import load_dotenv
from azure.cosmos import CosmosClient

load_dotenv(Path(__file__).resolve().parent / ".env", override=True)
raw = os.getenv("COSMOS_CONNECTION_STRING", "").strip().strip('"').strip("'")
parts = dict(seg.split("=", 1) for seg in raw.split(";") if "=" in seg)

endpoint = parts["AccountEndpoint"].strip()
key = parts["AccountKey"].strip()
print("Endpoint:", endpoint)
print("Key length:", len(key), "Ends with:", repr(key[-4:]))

client = CosmosClient(url=endpoint, credential=key)
print("Databases:", [d["id"] for d in client.list_databases()])
