"""Authentication router - register, login, refresh, logout."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth_middleware import get_current_user
from app.models.user import User
from app.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    LoginResponse,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
)
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=dict, status_code=201)
async def register(data: RegisterRequest, db: AsyncSession = Depends(get_db)):
    user, student = await auth_service.register_user(db, data.model_dump())
    await db.commit()
    return {"success": True, "message": "註冊成功", "data": {"user_id": user.id, "student_id": student.id}}

@router.post("/login", response_model=LoginResponse)
async def login(data: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await auth_service.login_user(db, data.email, data.password)
    await db.commit()
    return result


@router.post("/refresh", response_model=TokenResponse)
async def refresh(data: RefreshRequest, db: AsyncSession = Depends(get_db)):
    result = await auth_service.refresh_access_token(db, data.refresh_token)
    await db.commit()
    return result


@router.post("/logout")
async def logout(
    data: RefreshRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await auth_service.logout_user(db, data.refresh_token)
    await db.commit()
    return {"success": True, "message": "已登出"}


@router.post("/forgot-password")
async def forgot_password(data: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    """發送重設密碼連結（統一回應，避免帳號枚舉）。"""
    await auth_service.request_password_reset(db, data.email)
    await db.commit()
    return {"success": True, "message": "若此信箱或帳號存在，我們已發送重設密碼連結"}


@router.get("/reset-password/verify")
async def verify_reset_password(token: str, db: AsyncSession = Depends(get_db)):
    """驗證重設 token 是否有效。"""
    await auth_service.verify_reset_token(db, token)
    await db.commit()
    return {"success": True, "message": "Token 有效"}


@router.post("/reset-password")
async def reset_password(data: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    """使用 token 重設密碼。"""
    await auth_service.reset_password(db, data.token, data.new_password)
    await db.commit()
    return {"success": True, "message": "密碼重設成功，請重新登入"}