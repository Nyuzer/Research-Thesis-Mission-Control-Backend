from __future__ import annotations
import hashlib
import secrets
from typing import List
from fastapi import APIRouter, HTTPException, Depends, Request
from datetime import datetime, timezone
import uuid
from jose import JWTError

from .models import (
    LoginRequest, RefreshRequest, TokenResponse, UserCreate, UserUpdate,
    UserResponse, ProfileUpdate, UserRole,
    RobotKeyCreate, RobotKeyResponse, RobotKeyCreatedResponse,
)
from .database import users_collection, robot_api_keys_collection
from .password import hash_password, verify_password
from .jwt_handler import create_access_token, create_refresh_token, decode_token
from .dependencies import get_current_user, require_role
from .rate_limit import login_limiter, refresh_limiter

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest, request: Request):
    login_limiter.check(request)

    user_doc = users_collection.find_one({"email": req.email})
    if not user_doc or not verify_password(req.password, user_doc["hashed_password"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user_doc.get("is_active", True):
        raise HTTPException(status_code=403, detail="User is deactivated")

    users_collection.update_one(
        {"_id": user_doc["_id"]},
        {"$set": {"last_login": datetime.now(timezone.utc).isoformat()}},
    )

    token_data = {"sub": str(user_doc["_id"]), "role": user_doc["role"]}
    return TokenResponse(
        access_token=create_access_token(token_data),
        refresh_token=create_refresh_token(token_data),
        user=UserResponse(
            id=str(user_doc["_id"]),
            email=user_doc["email"],
            username=user_doc["username"],
            role=user_doc["role"],
            created_at=user_doc["created_at"],
            last_login=user_doc.get("last_login"),
            is_active=user_doc.get("is_active", True),
        ),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(req: RefreshRequest, request: Request):
    refresh_limiter.check(request)

    try:
        payload = decode_token(req.refresh_token)
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")
        user_id = payload.get("sub")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    user_doc = users_collection.find_one({"_id": user_id})
    if not user_doc:
        raise HTTPException(status_code=401, detail="User not found")
    if not user_doc.get("is_active", True):
        raise HTTPException(status_code=403, detail="User is deactivated")

    token_data = {"sub": str(user_doc["_id"]), "role": user_doc["role"]}
    return TokenResponse(
        access_token=create_access_token(token_data),
        refresh_token=create_refresh_token(token_data),
        user=UserResponse(
            id=str(user_doc["_id"]),
            email=user_doc["email"],
            username=user_doc["username"],
            role=user_doc["role"],
            created_at=user_doc["created_at"],
            last_login=user_doc.get("last_login"),
            is_active=user_doc.get("is_active", True),
        ),
    )


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: UserResponse = Depends(get_current_user)):
    return current_user


@router.put("/me", response_model=UserResponse)
async def update_me(
    data: ProfileUpdate,
    current_user: UserResponse = Depends(get_current_user),
):
    update_fields = {}
    if data.username is not None:
        update_fields["username"] = data.username
    if data.password is not None:
        update_fields["hashed_password"] = hash_password(data.password)

    if update_fields:
        users_collection.update_one({"_id": current_user.id}, {"$set": update_fields})

    user_doc = users_collection.find_one({"_id": current_user.id})
    return UserResponse(
        id=str(user_doc["_id"]),
        email=user_doc["email"],
        username=user_doc["username"],
        role=user_doc["role"],
        created_at=user_doc["created_at"],
        last_login=user_doc.get("last_login"),
        is_active=user_doc.get("is_active", True),
    )


# ── Admin-only user management ──


@router.get("/users", response_model=List[UserResponse])
async def list_users(
    _admin: UserResponse = Depends(require_role(UserRole.admin)),
):
    docs = users_collection.find()
    return [
        UserResponse(
            id=str(d["_id"]),
            email=d["email"],
            username=d["username"],
            role=d["role"],
            created_at=d["created_at"],
            last_login=d.get("last_login"),
            is_active=d.get("is_active", True),
        )
        for d in docs
    ]


@router.post("/users", response_model=UserResponse, status_code=201)
async def create_user(
    data: UserCreate,
    _admin: UserResponse = Depends(require_role(UserRole.admin)),
):
    if users_collection.find_one({"email": data.email}):
        raise HTTPException(status_code=409, detail="Email already registered")

    user_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "_id": user_id,
        "email": data.email,
        "username": data.username,
        "hashed_password": hash_password(data.password),
        "role": data.role.value,
        "created_at": now,
        "last_login": None,
        "is_active": True,
    }
    users_collection.insert_one(doc)
    return UserResponse(
        id=user_id,
        email=data.email,
        username=data.username,
        role=data.role,
        created_at=now,
        is_active=True,
    )


@router.put("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: str,
    data: UserUpdate,
    _admin: UserResponse = Depends(require_role(UserRole.admin)),
):
    user_doc = users_collection.find_one({"_id": user_id})
    if not user_doc:
        raise HTTPException(status_code=404, detail="User not found")

    update_fields = {}
    if data.email is not None:
        existing = users_collection.find_one({"email": data.email, "_id": {"$ne": user_id}})
        if existing:
            raise HTTPException(status_code=409, detail="Email already in use")
        update_fields["email"] = data.email
    if data.username is not None:
        update_fields["username"] = data.username
    if data.password is not None:
        update_fields["hashed_password"] = hash_password(data.password)
    if data.role is not None:
        update_fields["role"] = data.role.value
    if data.is_active is not None:
        update_fields["is_active"] = data.is_active

    if update_fields:
        users_collection.update_one({"_id": user_id}, {"$set": update_fields})

    user_doc = users_collection.find_one({"_id": user_id})
    return UserResponse(
        id=str(user_doc["_id"]),
        email=user_doc["email"],
        username=user_doc["username"],
        role=user_doc["role"],
        created_at=user_doc["created_at"],
        last_login=user_doc.get("last_login"),
        is_active=user_doc.get("is_active", True),
    )


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: str,
    admin: UserResponse = Depends(require_role(UserRole.admin)),
):
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")

    result = users_collection.delete_one({"_id": user_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    return {"detail": "User deleted"}


# ── Robot API key management (admin-only) ──


@router.post("/robot-keys", response_model=RobotKeyCreatedResponse, status_code=201)
async def create_robot_key(
    data: RobotKeyCreate,
    _admin: UserResponse = Depends(require_role(UserRole.admin)),
):
    raw_key = f"rk_{secrets.token_urlsafe(32)}"
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    key_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    doc = {
        "_id": key_id,
        "name": data.name,
        "robot_id": data.robot_id,
        "api_key_hash": key_hash,
        "key_prefix": raw_key[:10] + "...",
        "created_at": now,
    }
    robot_api_keys_collection.insert_one(doc)

    return RobotKeyCreatedResponse(
        id=key_id,
        name=data.name,
        robot_id=data.robot_id,
        key_prefix=doc["key_prefix"],
        created_at=now,
        api_key=raw_key,
    )


@router.get("/robot-keys", response_model=List[RobotKeyResponse])
async def list_robot_keys(
    _admin: UserResponse = Depends(require_role(UserRole.admin)),
):
    docs = robot_api_keys_collection.find()
    return [
        RobotKeyResponse(
            id=str(d["_id"]),
            name=d["name"],
            robot_id=d["robot_id"],
            key_prefix=d.get("key_prefix", ""),
            created_at=d["created_at"],
        )
        for d in docs
    ]


@router.delete("/robot-keys/{key_id}")
async def delete_robot_key(
    key_id: str,
    _admin: UserResponse = Depends(require_role(UserRole.admin)),
):
    result = robot_api_keys_collection.delete_one({"_id": key_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Robot key not found")
    return {"detail": "Robot key deleted"}
