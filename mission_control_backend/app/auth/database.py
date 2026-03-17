import os
from pymongo import MongoClient

MONGO_HOST = os.getenv("MONGO_HOST", "localhost")
MONGO_PORT = int(os.getenv("MONGO_DB_PORT", "27017"))

_client = MongoClient(MONGO_HOST, MONGO_PORT)
_db = _client["mission_control"]
users_collection = _db["users"]

# Ensure unique index on email
users_collection.create_index("email", unique=True)
