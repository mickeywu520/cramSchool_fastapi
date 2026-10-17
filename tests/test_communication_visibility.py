"""退選學生在數位聯絡簿的顯示規則（C 方案：讀取時過濾、資料保留）。"""

import shutil
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base
from app.models import (
    CommunicationCourseSession,
    CommunicationSessionStudent,
    Course,
    Enrollment,
    Student,
)
from app.routers.admin import _apply_session_content, _build_session_response
from app.schemas.communication_session import SessionCreateRequest, StudentSessionData
from app.services import communication_service
from app.services.attendance_service import TAIPEI_TZ


class CommunicationVisibilityTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.mkdtemp()
        database_path = Path(self.directory) / "comm.db"
        self.engine = create_async_engine(f"sqlite+aiosqlite:///{database_path.as_posix()}")
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        self.day = datetime.now(TAIPEI_TZ).date() - timedelta(days=3)
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    async def asyncTearDown(self):
        await self.engine.dispose()
        shutil.rmtree(self.directory, ignore_errors=True)

    async def seed(self):
        async with self.sessions() as db:
            student = Student(
                student_name="kid",
                gender="M",
                birth_date=date(2010, 1, 1),
                school="school",
                grade="5",
                parent_name="parent",
                phone="0912345678",
                card_number="A1111111",
                followup_status="在籍",
            )
            course = Course(
                name="math",
                category="subject",
                subject="math",
                days_of_week=str(self.day.isoweekday()),
                start_date=self.day - timedelta(days=30),
                end_date=self.day + timedelta(days=30),
                start_time="1830",
                end_time="1930",
                is_active=True,
                is_teaching=True,
            )
            db.add_all([student, course])
            await db.flush()
            db.add(Enrollment(student_id=student.id, course_id=course.id))
            await db.commit()
            return student.id, course.id

    async def create_session(self, student_id: int, course_id: int) -> int:
        async with self.sessions() as db:
            session = CommunicationCourseSession(course_id=course_id, entry_date=self.day)
            db.add(session)
            await db.flush()
            await _apply_session_content(db, session, SessionCreateRequest(
                course_id=course_id,
                entry_date=self.day,
                class_progress="prog",
                students=[StudentSessionData(student_id=student_id, exam_score=80)],
            ))
            await db.commit()
            return session.id

    async def remove_enrollment(self, student_id: int, course_id: int) -> None:
        """對應「選課管理」的移除（直接刪除選課列）。"""
        async with self.sessions() as db:
            enrollment = (await db.execute(
                select(Enrollment).where(
                    Enrollment.student_id == student_id,
                    Enrollment.course_id == course_id,
                )
            )).scalar_one()
            await db.delete(enrollment)
            await db.commit()

    async def set_enrollment_status(self, student_id: int, course_id: int, status: str) -> None:
        async with self.sessions() as db:
            enrollment = (await db.execute(
                select(Enrollment).where(
                    Enrollment.student_id == student_id,
                    Enrollment.course_id == course_id,
                )
            )).scalar_one()
            enrollment.status = status
            await db.commit()

    async def test_removed_student_hidden_but_record_kept(self):
        student_id, course_id = await self.seed()
        session_id = await self.create_session(student_id, course_id)

        async with self.sessions() as db:
            response = await _build_session_response(db, session_id)
            self.assertEqual([s.student_id for s in response.students], [student_id])

        await self.remove_enrollment(student_id, course_id)

        # 後台聯絡簿不再顯示
        async with self.sessions() as db:
            response = await _build_session_response(db, session_id)
            self.assertEqual(response.students, [])
            # 但資料仍在 DB
            records = (await db.execute(
                select(CommunicationSessionStudent).where(
                    CommunicationSessionStudent.session_id == session_id
                )
            )).scalars().all()
            self.assertEqual(len(records), 1)

    async def test_save_does_not_delete_hidden_records(self):
        student_id, course_id = await self.seed()
        session_id = await self.create_session(student_id, course_id)
        await self.set_enrollment_status(student_id, course_id, "dropped")

        # 模擬老師再存一次檔（畫面已看不到該生）→ 不可刪掉既有紀錄
        async with self.sessions() as db:
            session = (await db.execute(
                select(CommunicationCourseSession).where(
                    CommunicationCourseSession.id == session_id
                )
            )).scalar_one()
            await _apply_session_content(db, session, SessionCreateRequest(
                course_id=course_id,
                entry_date=self.day,
                students=[],
            ))
            await db.commit()

        async with self.sessions() as db:
            records = (await db.execute(
                select(CommunicationSessionStudent).where(
                    CommunicationSessionStudent.session_id == session_id
                )
            )).scalars().all()
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0].exam_score, 80)

        # 重新恢復選課後又會出現，證明資料沒被破壞
        await self.set_enrollment_status(student_id, course_id, "active")
        async with self.sessions() as db:
            response = await _build_session_response(db, session_id)
            self.assertEqual([s.student_id for s in response.students], [student_id])

    async def test_parent_view_hides_dropped_course(self):
        student_id, course_id = await self.seed()
        await self.create_session(student_id, course_id)

        async with self.sessions() as db:
            entries = await communication_service.get_session_entries(db, student_id)
            self.assertEqual(len(entries), 1)

        await self.set_enrollment_status(student_id, course_id, "dropped")

        async with self.sessions() as db:
            entries = await communication_service.get_session_entries(db, student_id)
            self.assertEqual(entries, [])


if __name__ == "__main__":
    unittest.main()
