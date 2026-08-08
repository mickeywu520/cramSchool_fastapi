"""Authentication service - registration, login, token management."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.models.refresh_token import RefreshToken
from app.models.student import Student
from app.models.teacher import Teacher
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
    """Register a new user with one or more student profiles."""
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

    # Build student list (multi-student or legacy flat fields)
    students_data = data.get("students") or []
    if not students_data:
        if data.get("student_name"):
            students_data = [{
                "student_name": data["student_name"],
                "gender": data["gender"],
                "birth_date": data["birth_date"],
                "school": data["school"],
                "grade": data["grade"],
                "class_name": data.get("class_name"),
                "id_number": data.get("id_number"),
            }]
    if not students_data:
        raise ConflictException("請至少填寫一位學生資料")

    created_students: list[Student] = []
    for idx, sdata in enumerate(students_data):
        # Generate student number
        student_count_result = await db.execute(select(Student).order_by(Student.id.desc()).limit(1))
        last_student = student_count_result.scalar_one_or_none()
        next_id = (last_student.id + 1) if last_student else 1
        student_number = f"HS{datetime.now().year}{next_id:04d}"

        # 每位學生：若填寫身分證字號，自動建立專屬帳號（帳號＝密碼＝身分證字號）
        id_number = (sdata.get("id_number") or "").strip()
        student_user_id = None
        if id_number:
            existing_student = (
                await db.execute(select(Student).where(Student.id_number == id_number).limit(1))
            ).scalar_one_or_none()
            if existing_student and existing_student.user_id:
                student_user_id = existing_student.user_id
            else:
                student_user = User(
                    email=None,
                    password_hash=hash_password(id_number),
                    role="student",
                    auth_provider="id_number",
                )
                db.add(student_user)
                await db.flush()
                student_user_id = student_user.id

        student = Student(
            user_id=student_user_id,
            parent_user_id=user.id,
            student_name=sdata["student_name"],
            gender=sdata["gender"],
            birth_date=sdata["birth_date"],
            school=sdata["school"],
            grade=sdata["grade"],
            class_name=sdata.get("class_name"),
            parent_name=data["parent_name"],
            parent_title=data.get("parent_title"),
            phone=data["phone"],
            parent2_name=data.get("parent2_name"),
            parent2_title=data.get("parent2_title"),
            parent2_phone=data.get("parent2_phone"),
            home_phone=data.get("home_phone"),
            id_number=sdata.get("id_number"),
            student_number=student_number,
            followup_status="待聯繫",
        )
        db.add(student)
        await db.flush()
        created_students.append(student)

    return user, created_students[0]


async def login_user(db: AsyncSession, email: str, password: str) -> dict:
    """Authenticate user with email or id_number and return tokens."""
    is_id_number = "@" not in email
    result = await db.execute(
        select(User)
        .options(selectinload(User.student), selectinload(User.teacher))
        .where(User.email == email)
    )
    user = result.scalar_one_or_none()

    # 舊資料相容：未找到帳號時，以身分證反查學生並補建/取得專屬帳號
    if not user and is_id_number:
        student_result = await db.execute(
            select(Student).where(Student.id_number == email).limit(1)
        )
        student = student_result.scalar_one_or_none()
        if student and student.user_id:
            account_result = await db.execute(
                select(User)
                .options(selectinload(User.student), selectinload(User.teacher))
                .where(User.id == student.user_id, User.auth_provider == "id_number")
            )
            user = account_result.scalar_one_or_none()
        if student and not user:
            account = User(
                email=None,
                password_hash=hash_password(student.id_number),
                role="student",
                auth_provider="id_number",
            )
            db.add(account)
            await db.flush()
            student.user_id = account.id
            user = account

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
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
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
        "auth_provider": user.auth_provider,
    }

    # 依 user_id 反查學生（避免 async lazy-load）
    student_result = await db.execute(
        select(Student).where(Student.user_id == user.id).limit(1)
    )
    student = student_result.scalar_one_or_none()
    if student:
        user_info["student_id"] = student.id
        user_info["student_name"] = student.student_name
    else:
        # 家長帳號：回傳第一位小孩資料，供前端顯示
        first_child_result = await db.execute(
            select(Student).where(Student.parent_user_id == user.id).order_by(Student.id.asc()).limit(1)
        )
        first_child = first_child_result.scalar_one_or_none()
        user_info["student_id"] = first_child.id if first_child else None
        user_info["student_name"] = first_child.student_name if first_child else None

    teacher_result = await db.execute(
        select(Teacher).where(Teacher.user_id == user.id).limit(1)
    )
    teacher = teacher_result.scalar_one_or_none()
    user_info["teacher_id"] = teacher.id if teacher else None
    user_info["teacher_name"] = teacher.name if teacher else None

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "user": user_info,
    }