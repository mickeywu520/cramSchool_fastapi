"""Authentication schemas."""

from datetime import date, datetime

from pydantic import BaseModel, EmailStr, Field


class StudentRegisterItem(BaseModel):
    student_name: str = Field(min_length=1, max_length=50)
    gender: str = Field(min_length=1, max_length=10)
    birth_date: date
    school: str = Field(min_length=1, max_length=100)
    grade: str = Field(min_length=1, max_length=20)
    class_name: str | None = None
    id_number: str | None = None


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)
    parent_name: str = Field(min_length=1, max_length=50)
    parent_title: str | None = None
    phone: str = Field(min_length=1, max_length=20)
    parent2_name: str | None = None
    parent2_title: str | None = None
    parent2_phone: str | None = None
    home_phone: str | None = None
    # 多學生註冊：最多 3 位小孩
    students: list[StudentRegisterItem] = Field(default_factory=list, min_length=0, max_length=3)
    # 相容舊版單學生欄位
    student_name: str | None = None
    gender: str | None = None
    birth_date: date | None = None
    school: str | None = None
    grade: str | None = None
    class_name: str | None = None
    id_number: str | None = None


class LoginRequest(BaseModel):
    email: str  # 信箱或身分證字號
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
    email: str | None = None
    role: str
    auth_provider: str | None = None
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