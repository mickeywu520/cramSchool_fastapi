"""Authentication schemas."""

from datetime import date, datetime

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)
    student_name: str = Field(min_length=1, max_length=50)
    birth_date: date
    parent_name: str = Field(min_length=1, max_length=50)
    phone: str = Field(min_length=1, max_length=20)
    grade: str = Field(min_length=1, max_length=20)
    school: str = Field(min_length=1, max_length=100)
    interested_subjects: list[str] = Field(default_factory=list)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class FirebaseAuthRequest(BaseModel):
    id_token: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class UserInfo(BaseModel):
    id: int
    email: str
    role: str
    student_id: int | None = None
    student_name: str | None = None
    teacher_id: int | None = None
    teacher_name: str | None = None


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserInfo