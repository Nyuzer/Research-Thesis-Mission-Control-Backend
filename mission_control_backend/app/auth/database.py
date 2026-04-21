import os
from pymongo import MongoClient

MONGO_HOST = os.getenv("MONGO_HOST", "localhost")
MONGO_PORT = int(os.getenv("MONGO_DB_PORT", "27017"))

_client = MongoClient(MONGO_HOST, MONGO_PORT)
_db = _client["mission_control"]
users_collection = _db["users"]
robot_api_keys_collection = _db["robot_api_keys"]

# Ensure unique index on email
users_collection.create_index("email", unique=True)
# Ensure unique index on api_key_hash for fast lookups
robot_api_keys_collection.create_index("api_key_hash", unique=True)
