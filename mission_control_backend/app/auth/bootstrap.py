import logging
from datetime import datetime, timezone
import uuid
from .database import users_collection
from .password import hash_password
from .config import ADMIN_EMAIL, ADMIN_PASSWORD, ADMIN_USERNAME

logger = logging.getLogger(__name__)


def create_default_admin():
    """Create default admin user on startup if no users exist."""
    if users_collection.count_documents({}) > 0:
        logger.info("Users already exist, skipping admin bootstrap")
        return

    admin_doc = {
        "_id": str(uuid.uuid4()),
        "email": ADMIN_EMAIL,
        "username": ADMIN_USERNAME,
        "hashed_password": hash_password(ADMIN_PASSWORD),
        "role": "admin",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "last_login": None,
        "is_active": True,
    }
    users_collection.insert_one(admin_doc)
    logger.info(f"Default admin user created: {ADMIN_EMAIL}")
