"""Database seed data initializer.

Only seeds the default admin account.
All other data (banners, teachers, honors, etc.) must be created via the admin UI.

Usage:
    python -m app.seed
"""

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session, init_db
from app.models.user import User
from app.utils.security import hash_password


async def is_empty(db: AsyncSession, model) -> bool:
    result = await db.execute(select(model).limit(1))
    return result.scalar_one_or_none() is None


async def seed_database():
    await init_db()
    async with async_session() as db:
        try:
            if await is_empty(db, User):
                admin = User(
                    email="admin@cramschool.com",
                    password_hash=hash_password("admin"),
                    role="admin",
                    auth_provider="email",
                    is_active=True,
                )
                db.add(admin)
                await db.commit()
                print("Default admin account created: admin@cramschool.com / admin")
            else:
                print("Admin account already exists, skipping.")
        except Exception as e:
            await db.rollback()
            print(f"Seed failed: {e}")
            raise


if __name__ == "__main__":
    asyncio.run(seed_database())
