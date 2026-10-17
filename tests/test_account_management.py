import shutil
import tempfile
import unittest
from datetime import date
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base
from app.models import (
    CommunicationBookEntry,
    CommunicationSessionStudent,
    Course,
    Enrollment,
    HomeworkRecord,
    Student,
    User,
)
from app.models.communication_session import CommunicationCourseSession
from app.services import account_service
from app.utils.exceptions import AppException


class AccountManagementTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.mkdtemp()
        db_path = Path(self.directory) / "accounts.db"
        self.engine = create_async_engine(f"sqlite+aiosqlite:///{db_path.as_posix()}")
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def asyncTearDown(self):
        await self.engine.dispose()
        shutil.rmtree(self.directory, ignore_errors=True)

    async def _seed_parent_with_student(self, enrolled: bool):
        """建立 1 個家長帳號 + 1 位學生（+ 1 門課，可控制是否在籍選課）。"""
        async with self.sessions() as db:
            parent = User(email="parent@example.com", role="student", auth_provider="email")
            student_user = User(email=None, role="student", auth_provider="id_number")
            db.add_all([parent, student_user])
            await db.flush()

            course = Course(name="math", category="subject", subject="math", is_active=True)
            db.add(course)
            await db.flush()

            student = Student(
                user_id=student_user.id,
                parent_user_id=parent.id,
                student_name="小禾",
                gender="M",
                birth_date=date(2010, 1, 1),
                school="school",
                grade="5",
                parent_name="禾爸",
                phone="0912345678",
                id_number="A123456789",
                followup_status="在籍",
            )
            db.add(student)
            await db.flush()

            if enrolled:
                db.add(Enrollment(student_id=student.id, course_id=course.id, status="active"))

            session = CommunicationCourseSession(course_id=course.id, entry_date=date(2026, 1, 1))
            db.add(session)
            await db.flush()
            db.add(CommunicationSessionStudent(session_id=session.id, student_id=student.id))
            entry = CommunicationBookEntry(student_id=student.id, entry_date=date(2026, 1, 1))
            db.add(entry)
            await db.flush()
            db.add(HomeworkRecord(communication_book_id=entry.id, subject="math", content="x"))
            await db.commit()
            return parent.id, student.id, student_user.id

    async def test_list_accounts_shows_parent_and_student(self):
        await self._seed_parent_with_student(enrolled=True)
        async with self.sessions() as db:
            parents = await account_service.list_accounts(db, account_type="parent")
            self.assertEqual(len(parents), 1)
            self.assertEqual(parents[0]["display_name"], "禾爸")
            self.assertEqual(parents[0]["students"][0]["student_name"], "小禾")
            self.assertEqual(parents[0]["students"][0]["active_course_count"], 1)

            students = await account_service.list_accounts(db, account_type="student")
            self.assertEqual(len(students), 1)
            self.assertEqual(students[0]["login_id"], "A123456789")

    async def test_delete_blocked_when_student_still_enrolled(self):
        parent_id, _, _ = await self._seed_parent_with_student(enrolled=True)
        async with self.sessions() as db:
            with self.assertRaises(AppException) as ctx:
                await account_service.delete_account(db, parent_id)
            self.assertEqual(ctx.exception.code, "STUDENT_STILL_ENROLLED")
            self.assertEqual(ctx.exception.status_code, 409)
            self.assertEqual(ctx.exception.details[0]["courses"], ["math"])
            # 未被刪除
            self.assertIsNotNone(await db.get(User, parent_id))

    async def test_delete_removes_account_students_and_children(self):
        parent_id, student_id, student_user_id = await self._seed_parent_with_student(enrolled=False)
        async with self.sessions() as db:
            result = await account_service.delete_account(db, parent_id)
            await db.commit()
            self.assertTrue(result["success"])
            self.assertEqual(result["deleted_students"], 1)

        async with self.sessions() as db:
            self.assertIsNone(await db.get(User, parent_id))
            self.assertIsNone(await db.get(Student, student_id))
            # 學生的身分證帳號已無依附學生 → 一併刪除（不再留孤兒空帳號列）
            self.assertIsNone(await db.get(User, student_user_id))
            for model in (Enrollment, CommunicationSessionStudent, CommunicationBookEntry, HomeworkRecord):
                count = await db.scalar(select(func.count()).select_from(model))
                self.assertEqual(count, 0, f"{model.__tablename__} 未清空")


if __name__ == "__main__":
    unittest.main()
