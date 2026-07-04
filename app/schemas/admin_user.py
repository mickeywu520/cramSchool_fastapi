"""Schemas for admin user management."""

from datetime import datetime

from pydantic import BaseModel


class AdminUserResponse(BaseModel):
    id: int
    email: str
    role: str
    is_active: bool
    last_login_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AdminUserCreateRequest(BaseModel):
    email: str
    password: str
    role: str = "maintainer"


class AdminUserUpdateRequest(BaseModel):
    role: str | None = None
    is_active: bool | None = None


class AdminUserResetPasswordRequest(BaseModel):
    password: str
