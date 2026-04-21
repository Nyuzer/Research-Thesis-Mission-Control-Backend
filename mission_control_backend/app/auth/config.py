import os
import sys
import logging
from pathlib import Path
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load .env — search from this file's directory upward
_dir = Path(__file__).resolve().parent
while _dir != _dir.parent:
    _candidate = _dir / ".env"
    if _candidate.exists():
        load_dotenv(_candidate)
        break
    _dir = _dir.parent


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        logger.critical(f"Required environment variable {name} is not set. Exiting.")
        sys.exit(1)
    return value


SECRET_KEY = _require_env("AUTH_SECRET_KEY")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))

ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@missioncontrol.local")
ADMIN_PASSWORD = _require_env("ADMIN_PASSWORD")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
