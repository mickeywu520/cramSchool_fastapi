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
from app.schemas.punch import GcpPunchEvent
from app.services.attendance_service import TAIPEI_TZ, ingest_events


class SessionFillTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.mkdtemp()
        database_path = Path(self.directory) / "session.db"
        self.engine = create_async_engine(f"sqlite+aiosqlite:///{database_path.as_posix()}")
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        self.day = datetime.now(TAIPEI_TZ).date() - timedelta(days=14)
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

    async def punch(self):
        async with self.sessions() as db:
            results = await ingest_events(db, [GcpPunchEvent(
                event_id="s1",
                occurred_at=f"{self.day.isoformat()}T18:32:00+08:00",
                received_at=f"{self.day.isoformat()}T18:32:00+08:00",
                event={"function_code": 11, "event_code": "M11"},
                card={"uid_hex": "00000000A1111111", "uid_decimal": int("A1111111", 16)},
                device={"node_id": 1, "ip": "127.0.0.1"},
            )])
            await db.commit()
            self.assertEqual(results[0]["status"], "ok")

    async def test_teacher_fills_punch_generated_session(self):
        student_id, course_id = await self.seed()
        await self.punch()

        async with self.sessions() as db:
            session = (await db.execute(
                select(CommunicationCourseSession)
            )).scalar_one()
            self.assertTrue(session.punch_generated)

            await _apply_session_content(db, session, SessionCreateRequest(
                course_id=course_id,
                entry_date=self.day,
                class_progress="today covered fractions",
                students=[StudentSessionData(student_id=student_id, exam_score=95)],
            ))
            await db.commit()

        async with self.sessions() as db:
            session = (await db.execute(
                select(CommunicationCourseSession)
            )).scalar_one()
            self.assertTrue(session.punch_generated)
            self.assertEqual(session.class_progress, "today covered fractions")
            records = (await db.execute(
                select(CommunicationSessionStudent).where(
                    CommunicationSessionStudent.session_id == session.id
                )
            )).scalars().all()
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0].exam_score, 95)

            response = await _build_session_response(db, session.id)
            self.assertTrue(response.punch_generated)
            by_id = {s.student_id: s for s in response.students}
            self.assertEqual(by_id[student_id].arrival_time, "18:32")


if __name__ == "__main__":
    unittest.main()
