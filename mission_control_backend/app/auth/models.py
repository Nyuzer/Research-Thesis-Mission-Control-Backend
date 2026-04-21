from pydantic import BaseModel, field_validator
from typing import Optional, List
from enum import Enum


class UserRole(str, Enum):
    admin = "admin"
    operator = "operator"
    viewer = "viewer"
    robot = "robot"


def _validate_password(v: str) -> str:
    if len(v) < 8:
        raise ValueError("Password must be at least 8 characters long")
    if not any(c.isalpha() for c in v):
        raise ValueError("Password must contain at least one letter")
    if not any(c.isdigit() for c in v):
        raise ValueError("Password must contain at least one digit")
    return v


class UserInDB(BaseModel):
    id: str
    email: str
    username: str
    hashed_password: str
    role: UserRole = UserRole.viewer
    created_at: str
    last_login: Optional[str] = None
    is_active: bool = True


class UserCreate(BaseModel):
    email: str
    username: str
    password: str
    role: UserRole = UserRole.viewer

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        return _validate_password(v)


class UserUpdate(BaseModel):
    email: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            return _validate_password(v)
        return v


class UserResponse(BaseModel):
    id: str
    email: str
    username: str
    role: UserRole
    created_at: str
    last_login: Optional[str] = None
    is_active: bool = True


class LoginRequest(BaseModel):
    email: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserResponse


class ProfileUpdate(BaseModel):
    username: Optional[str] = None
    password: Optional[str] = None

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            return _validate_password(v)
        return v


# Robot API key models
class RobotKeyCreate(BaseModel):
    name: str
    robot_id: str


class RobotKeyResponse(BaseModel):
    id: str
    name: str
    robot_id: str
    key_prefix: str
    created_at: str


class RobotKeyCreatedResponse(RobotKeyResponse):
    api_key: str
