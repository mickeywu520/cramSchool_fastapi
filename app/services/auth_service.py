"""Authentication service - registration, login, token management."""

import json
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.refresh_token import RefreshToken
from app.models.student import Student
from app.models.user import User
from app.utils.exceptions import ConflictException, UnauthorizedException
from app.utils.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


async def register_user(db: AsyncSession, data: dict) -> tuple[User, Student]:
    """Register a new user with student profile."""
    # Check if email already exists
    result = await db.execute(select(User).where(User.email == data["email"]))
    if result.scalar_one_or_none():
        raise ConflictException("此信箱已被註冊")

    # Create user
    user = User(
        email=data["email"],
        password_hash=hash_password(data["password"]),
        role="student",
        auth_provider="email",
    )
    db.add(user)
    await db.flush()

    # Generate student number
    student_count_result = await db.execute(select(Student).order_by(Student.id.desc()).limit(1))
    last_student = student_count_result.scalar_one_or_none()
    next_id = (last_student.id + 1) if last_student else 1
    student_number = f"HS{datetime.now().year}{next_id:04d}"

    # Create student profile
    student = Student(
        user_id=user.id,
        student_name=data["student_name"],
        birth_date=data["birth_date"],
        parent_name=data["parent_name"],
        phone=data["phone"],
        grade=data["grade"],
        school=data["school"],
        interested_subjects=json.dumps(data.get("interested_subjects", []), ensure_ascii=False),
        student_number=student_number,
    )
    db.add(student)
    await db.flush()

    return user, student


async def login_user(db: AsyncSession, email: str, password: str) -> dict:
    """Authenticate user with email/password and return tokens."""
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if not user or not user.password_hash:
        raise UnauthorizedException("信箱或密碼錯誤")

    if not verify_password(password, user.password_hash):
        raise UnauthorizedException("信箱或密碼錯誤")

    if not user.is_active:
        raise UnauthorizedException("帳號已被停用")

    return await _generate_tokens(db, user)


async def refresh_access_token(db: AsyncSession, refresh_token_str: str) -> dict:
    """Validate refresh token and issue new access token."""
    try:
        payload = decode_token(refresh_token_str)
    except ValueError:
        raise UnauthorizedException("Invalid refresh token")

    if payload.get("type") != "refresh":
        raise UnauthorizedException("Invalid token type")

    token_id = payload.get("jti")
    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.id == token_id,
            RefreshToken.is_revoked == False,
        )
    )
    token_record = result.scalar_one_or_none()

    if not token_record or token_record.expires_at < datetime.now(timezone.utc):
        raise UnauthorizedException("Refresh token expired or revoked")

    # Revoke old refresh token
    token_record.is_revoked = True

    # Get user
    user_result = await db.execute(select(User).where(User.id == token_record.user_id))
    user = user_result.scalar_one_or_none()
    if not user or not user.is_active:
        raise UnauthorizedException("User not found or inactive")

    return await _generate_tokens(db, user)


async def logout_user(db: AsyncSession, refresh_token_str: str):
    """Revoke a refresh token."""
    try:
        payload = decode_token(refresh_token_str)
    except ValueError:
        return

    token_id = payload.get("jti")
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.id == token_id)
    )
    token_record = result.scalar_one_or_none()
    if token_record:
        token_record.is_revoked = True


async def _generate_tokens(db: AsyncSession, user: User) -> dict:
    """Generate access + refresh tokens and store refresh token."""
    # Update last login
    user.last_login_at = datetime.now(timezone.utc)

    # Create refresh token record
    refresh_token_record = RefreshToken(
        user_id=user.id,
        token="",  # placeholder, will update after creation
        expires_at=datetime.now(timezone.utc).replace(
            day=datetime.now(timezone.utc).day + settings.REFRESH_TOKEN_EXPIRE_DAYS
        ),
    )
    db.add(refresh_token_record)
    await db.flush()

    # Generate tokens
    access_token = create_access_token(user.id, user.role)
    refresh_token = create_refresh_token(user.id, refresh_token_record.id)

    # Update refresh token record with actual token
    refresh_token_record.token = refresh_token

    # Build user info
    user_info = {
        "id": user.id,
        "email": user.email,
        "role": user.role,
    }

    if user.student:
        user_info["student_id"] = user.student.id
        user_info["student_name"] = user.student.student_name
    else:
        user_info["student_id"] = None
        user_info["student_name"] = None

    if user.teacher:
        user_info["teacher_id"] = user.teacher.id
        user_info["teacher_name"] = user.teacher.name
    else:
        user_info["teacher_id"] = None
        user_info["teacher_name"] = None

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "user": user_info,
    }