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
    """Add new columns if they don't exist (SQLite compat)."""
    table_columns = {
        "students": {
            "gender": "VARCHAR(10) NOT NULL DEFAULT ''",
            "class_name": "VARCHAR(20)",
            "parent2_phone": "VARCHAR(20)",
            "home_phone": "VARCHAR(20)",
            "id_number": "VARCHAR(20)",
            "branch_id": "INTEGER REFERENCES branches(id)",
            "followup_status": "VARCHAR(20) NOT NULL DEFAULT '待聯繫'",
            "parent_title": "VARCHAR(10)",
            "parent2_name": "VARCHAR(50)",
            "parent2_title": "VARCHAR(10)",
        },
        "courses": {
            "grade_level": "VARCHAR(20)",
            "day_of_week": "INTEGER",
            "days_of_week": "VARCHAR(20)",
            "start_date": "DATE",
            "end_date": "DATE",
            "start_time": "VARCHAR(10)",
            "end_time": "VARCHAR(10)",
            "location": "VARCHAR(50)",
            "branch_id": "INTEGER REFERENCES branches(id)",
            "school_year": "VARCHAR(10)",
            "semester": "VARCHAR(10)",
            "is_teaching": "BOOLEAN NOT NULL DEFAULT 1",
        },
        "teachers": {
            "branch_id": "INTEGER REFERENCES branches(id)",
        },
        "communication_session_students": {
            "handout_status": "VARCHAR(10)",
            "vocab": "VARCHAR(10)",
            "reschedule_date": "DATE",
            "homework_material": "VARCHAR(10)",
            "homework_workbook": "VARCHAR(10)",
        },
    }
    async with engine.begin() as conn:
        for table, columns in table_columns.items():
            for col_name, col_type in columns.items():
                try:
                    await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}"))
                    logger.info(f"Added column '{table}.{col_name}'")
                except Exception:
                    pass  # column already exists


async def _drop_old_columns():
    """Drop renamed columns that still exist from old schema."""
    drops = [
        ("communication_session_students", "handout_completed"),
    ]
    async with engine.begin() as conn:
        for table, col in drops:
            try:
                await conn.execute(text(f"ALTER TABLE {table} DROP COLUMN {col}"))
                logger.info(f"Dropped column '{table}.{col}'")
            except Exception:
                pass  # column may not exist or SQLite version < 3.35.0


async def init_db():
    """Create all tables and run migrations. Call on startup."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await _add_missing_columns()
    await _drop_old_columns()