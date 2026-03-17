from pydantic import BaseModel, EmailStr
from typing import Optional
from enum import Enum


class UserRole(str, Enum):
    admin = "admin"
    operator = "operator"
    viewer = "viewer"


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


class UserUpdate(BaseModel):
    email: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None


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


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserResponse


class ProfileUpdate(BaseModel):
    username: Optional[str] = None
    password: Optional[str] = None
