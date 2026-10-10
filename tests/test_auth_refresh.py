import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base
from app.models import RefreshToken, User
from app.services import auth_service
from app.utils.exceptions import UnauthorizedException
from app.utils.security import create_refresh_token


class AuthRefreshTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.mkdtemp()
        db_path = Path(self.directory) / "auth.db"
        self.engine = create_async_engine(f"sqlite+aiosqlite:///{db_path.as_posix()}")
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def asyncTearDown(self):
        await self.engine.dispose()
        shutil.rmtree(self.directory, ignore_errors=True)

    async def _user_with_refresh(self, days: int = 30):
        async with self.sessions() as db:
            user = User(role="admin", is_active=True)
            db.add(user)
            await db.flush()
            record = RefreshToken(
                user_id=user.id,
                token="",
                expires_at=datetime.now(timezone.utc) + timedelta(days=days),
            )
            db.add(record)
            await db.flush()
            token = create_refresh_token(user.id, record.id)
            record.token = token
            await db.commit()
            return user.id, token

    async def test_refresh_succeeds_for_valid_token(self):
        # 回歸：先前 naive/aware 比較會 TypeError → refresh 回 500。
        _, token = await self._user_with_refresh()
        async with self.sessions() as db:
            result = await auth_service.refresh_access_token(db, token)
            await db.commit()
        self.assertIn("access_token", result)
        self.assertIn("refresh_token", result)
        self.assertTrue(result["access_token"])

    async def test_refresh_rotates_and_revokes_old(self):
        _, token = await self._user_with_refresh()
        async with self.sessions() as db:
            await auth_service.refresh_access_token(db, token)
            await db.commit()
        # 舊 refresh token 已被撤銷 → 重用應被拒
        async with self.sessions() as db:
            with self.assertRaises(UnauthorizedException):
                await auth_service.refresh_access_token(db, token)

    async def test_refresh_rejects_expired_refresh(self):
        _, token = await self._user_with_refresh(days=-1)
        async with self.sessions() as db:
            with self.assertRaises(UnauthorizedException):
                await auth_service.refresh_access_token(db, token)

    async def test_refresh_rejects_unknown_token(self):
        async with self.sessions() as db:
            with self.assertRaises(UnauthorizedException):
                await auth_service.refresh_access_token(db, "not-a-jwt")


if __name__ == "__main__":
    unittest.main()
