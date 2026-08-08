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
            "remark": "TEXT",
            "parent_user_id": "INTEGER REFERENCES users(id)",
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
            "tutoring_day_of_week": "INTEGER",
            "tutoring_days_of_week": "VARCHAR(20)",
            "tutoring_start_time": "VARCHAR(10)",
            "tutoring_end_time": "VARCHAR(10)",
            "tutoring_location": "VARCHAR(50)",
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
        "banners": {
            "subtitle": "VARCHAR(200)",
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


async def _migrate_students_nullable_user_id():
    """Rebuild students table so user_id is nullable + add parent_user_id (SQLite)."""
    async with engine.begin() as conn:
        info_result = await conn.execute(text("PRAGMA table_info(students)"))
        rows = info_result.fetchall()
        cols = {row[1]: row for row in rows}
        if "user_id" not in cols:
            return
        # row: cid, name, type, notnull, dflt_value, pk
        if cols["user_id"][3] == 0:
            return  # already nullable

        await conn.execute(text("PRAGMA foreign_keys=OFF"))
        try:
            col_defs = []
            for r in rows:
                cid, name, ctype, notnull, dflt, pk = r
                if name == "user_id":
                    col_defs.append(f'"user_id" INTEGER UNIQUE REFERENCES users(id)')
                elif name == "parent_user_id":
                    continue
                else:
                    parts = [f'"{name}" {ctype}']
                    if notnull and name not in ("user_id",):
                        parts.append("NOT NULL")
                    if dflt is not None:
                        parts.append(f"DEFAULT {dflt}")
                    if pk:
                        parts.append("PRIMARY KEY AUTOINCREMENT")
                    col_defs.append(" ".join(parts))
            col_defs.append('"parent_user_id" INTEGER REFERENCES users(id)')
            create_sql = f'CREATE TABLE "students_new" ({", ".join(col_defs)})'
            await conn.execute(text(create_sql))

            copy_cols = [r[1] for r in rows]
            insert_sql = (
                'INSERT INTO "students_new" (' + ", ".join(f'"{c}"' for c in copy_cols) + ") "
                "SELECT " + ", ".join(f'"{c}"' for c in copy_cols) + " FROM students"
            )
            await conn.execute(text(insert_sql))

            await conn.execute(text('DROP TABLE "students"'))
            await conn.execute(text('ALTER TABLE "students_new" RENAME TO "students"'))
            logger.info("Rebuilt 'students' table: user_id nullable + parent_user_id added")
        finally:
            await conn.execute(text("PRAGMA foreign_keys=ON"))


async def _migrate_users_nullable_email():
    """Rebuild users table so email is nullable (SQLite)."""
    async with engine.begin() as conn:
        info_result = await conn.execute(text("PRAGMA table_info(users)"))
        rows = info_result.fetchall()
        cols = {row[1]: row for row in rows}
        if "email" not in cols:
            return
        # row: cid, name, type, notnull, dflt_value, pk
        if cols["email"][3] == 0:
            return  # already nullable

        await conn.execute(text("PRAGMA foreign_keys=OFF"))
        try:
            col_defs = []
            for r in rows:
                cid, name, ctype, notnull, dflt, pk = r
                if name == "email":
                    col_defs.append(f'"email" VARCHAR(255) UNIQUE')
                else:
                    parts = [f'"{name}" {ctype}']
                    if notnull and name not in ("email",):
                        parts.append("NOT NULL")
                    if dflt is not None:
                        parts.append(f"DEFAULT {dflt}")
                    if pk:
                        parts.append("PRIMARY KEY AUTOINCREMENT")
                    col_defs.append(" ".join(parts))
            create_sql = f'CREATE TABLE "users_new" ({", ".join(col_defs)})'
            await conn.execute(text(create_sql))

            copy_cols = [r[1] for r in rows]
            insert_sql = (
                'INSERT INTO "users_new" (' + ", ".join(f'"{c}"' for c in copy_cols) + ") "
                "SELECT " + ", ".join(f'"{c}"' for c in copy_cols) + " FROM users"
            )
            await conn.execute(text(insert_sql))

            await conn.execute(text('DROP TABLE "users"'))
            await conn.execute(text('ALTER TABLE "users_new" RENAME TO "users"'))
            logger.info("Rebuilt 'users' table: email nullable")
        finally:
            await conn.execute(text("PRAGMA foreign_keys=ON"))


async def _clear_id_number_account_email():
    """清空以身分證字號為 email 的學生帳號 email（登入識別改為 students.id_number）。"""
    async with engine.begin() as conn:
        await conn.execute(
            text("UPDATE users SET email = NULL WHERE auth_provider = 'id_number'")
        )
        logger.info("Cleared email for id_number student accounts")


async def init_db():
    """Create all tables and run migrations. Call on startup."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await _migrate_students_nullable_user_id()
    await _migrate_users_nullable_email()
    await _add_missing_columns()
    await _clear_id_number_account_email()
    await _drop_old_columns()