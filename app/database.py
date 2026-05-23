"""SQLAlchemy async engine and session configuration."""

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

logger = logging.getLogger(__name__)

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    connect_args={"check_same_thread": False},
)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    """Dependency that provides an async database session."""
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def _add_missing_columns():
    """Add new columns to students table if they don't exist (SQLite compat)."""
    new_columns = {
        "gender": "VARCHAR(10) NOT NULL DEFAULT ''",
        "class_name": "VARCHAR(20)",
        "parent2_phone": "VARCHAR(20)",
        "home_phone": "VARCHAR(20)",
        "id_number": "VARCHAR(20)",
    }
    async with engine.begin() as conn:
        for col_name, col_type in new_columns.items():
            try:
                await conn.execute(text(f"ALTER TABLE students ADD COLUMN {col_name} {col_type}"))
                logger.info(f"Added column 'students.{col_name}'")
            except Exception:
                pass  # column already exists


async def init_db():
    """Create all tables and run migrations. Call on startup."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await _add_missing_columns()