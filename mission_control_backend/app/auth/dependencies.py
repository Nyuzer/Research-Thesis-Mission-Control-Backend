from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError
from .jwt_handler import decode_token
from .database import users_collection
from .models import UserResponse, UserRole

security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> UserResponse:
    token = credentials.credentials
    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token type")
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user_doc = users_collection.find_one({"_id": user_id})
    if user_doc is None:
        raise HTTPException(status_code=401, detail="User not found")
    if not user_doc.get("is_active", True):
        raise HTTPException(status_code=403, detail="User is deactivated")

    return UserResponse(
        id=str(user_doc["_id"]),
        email=user_doc["email"],
        username=user_doc["username"],
        role=user_doc["role"],
        created_at=user_doc["created_at"],
        last_login=user_doc.get("last_login"),
        is_active=user_doc.get("is_active", True),
    )


def require_role(*roles: UserRole):
    async def role_checker(
        current_user: UserResponse = Depends(get_current_user),
    ) -> UserResponse:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=403,
                detail=f"Requires one of roles: {[r.value for r in roles]}",
            )
        return current_user
    return role_checker
