"""JWT authentication dependency injection for FastAPI."""

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.utils.exceptions import ForbiddenException, UnauthorizedException
from app.utils.security import decode_token

security_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Extract and validate JWT token, return current user."""
    if credentials is None:
        raise UnauthorizedException("Missing authentication token")

    try:
        payload = decode_token(credentials.credentials)
    except ValueError:
        raise UnauthorizedException("Invalid or expired token")

    if payload.get("type") != "access":
        raise UnauthorizedException("Invalid token type")

    user_id = int(payload.get("sub"))
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        raise UnauthorizedException("User not found or inactive")

    return user


def require_role(*roles: str):
    """Dependency factory: require one of the given roles."""

    async def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles:
            raise ForbiddenException(f"Requires one of roles: {roles}")
        return current_user

    return role_checker


# Pre-built role dependencies
require_student = require_role("student")
require_teacher = require_role("teacher")
require_admin = require_role("admin")
require_teacher_or_admin = require_role("teacher", "admin")
require_any_authenticated = require_role("student", "teacher", "admin")