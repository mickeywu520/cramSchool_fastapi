import shutil
import tempfile
import unittest
from datetime import date, datetime, time, timedelta
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base
from app.models import (
    AttendanceDaily,
    ClassAttendance,
    Course,
    Enrollment,
    LeaveApplication,
    MakeupClass,
    PunchRawEvent,
    Student,
)
from app.schemas.punch import GcpPunchEvent
from app.services.attendance_service import (
    TAIPEI_TZ,
    get_class_attendance,
    ingest_events,
)


class AttendanceServiceTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.mkdtemp()
        database_path = Path(self.directory) / "attendance.db"
        self.engine = create_async_engine(f"sqlite+aiosqlite:///{database_path.as_posix()}")
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        self.day = datetime.now(TAIPEI_TZ).date() - timedelta(days=14)
        self.weekday = str(self.day.isoweekday())
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    async def asyncTearDown(self):
        await self.engine.dispose()
        shutil.rmtree(self.directory, ignore_errors=True)

    def student(self, name, card):
        return Student(
            student_name=name,
            gender="M",
            birth_date=date(2010, 1, 1),
            school="school",
            grade="5",
            parent_name="parent",
            phone="0912345678",
            card_number=card,
            followup_status="\u5728\u7c4d",
        )

    def course(self, name, start_time, end_time):
        return Course(
            name=name,
            category="subject",
            subject="math",
            days_of_week=self.weekday,
            start_date=self.day - timedelta(days=30),
            end_date=self.day + timedelta(days=30),
            start_time=start_time,
            end_time=end_time,
            is_active=True,
            is_teaching=True,
        )

    def event(self, event_id, at, card, code="M11", include_hi_lo=False):
        payload = {"uid_hex": "00000000" + card, "uid_decimal": int(card, 16)}
        if include_hi_lo:
            payload["card_number_hi"] = int(card[:4], 16)
            payload["card_number_lo"] = int(card[4:], 16)
        return GcpPunchEvent(
            event_id=event_id,
            occurred_at=at,
            received_at=at,
            event={"function_code": 11, "event_code": code},
            card=payload,
            device={"node_id": 1, "ip": "127.0.0.1"},
        )

    async def seed(self):
        async with self.sessions() as db:
            first = self.student("first", "A1111111")
            second = self.student("second", "A2222222")
            third = self.student("third", "A3333333")
            first_course = self.course("first", "1830", "1930")
            second_course = self.course("second", "1930", "2030")
            db.add_all([first, second, third, first_course, second_course])
            await db.flush()
            db.add_all(
                [
                    Enrollment(student_id=first.id, course_id=first_course.id),
                    Enrollment(student_id=first.id, course_id=second_course.id),
                    Enrollment(student_id=second.id, course_id=first_course.id),
                    Enrollment(student_id=third.id, course_id=first_course.id),
                ]
            )
            await db.commit()
            return first.id, second.id, third.id, first_course.id, second_course.id

    async def test_m03_is_attendance_and_idempotent(self):
        first_id, _, _, course_id, _ = await self.seed()
        event = self.event(
            "m03",
            f"{self.day.isoformat()}T18:00:00+08:00",
            "A1111111",
            code="M03",
        )
        async with self.sessions() as db:
            results = await ingest_events(db, [event])
            await db.commit()
            self.assertEqual(results[0]["status"], "ok")
            self.assertEqual(results[0]["attendance_status"], "on_time")
            self.assertEqual(results[0]["course_id"], course_id)
            class_id = results[0]["class_attendance_id"]
            raw = (
                await db.execute(select(PunchRawEvent).where(PunchRawEvent.event_id == "m03"))
            ).scalar_one()
            daily = (
                await db.execute(
                    select(AttendanceDaily).where(AttendanceDaily.student_id == first_id)
                )
            ).scalar_one()
            self.assertEqual(raw.class_attendance_id, class_id)
            self.assertEqual(daily.punch_count, 1)
        async with self.sessions() as db:
            results = await ingest_events(db, [event])
            await db.commit()
            self.assertEqual(results[0]["status"], "duplicate")
            self.assertFalse(results[0]["stored"])
            self.assertEqual(await db.scalar(select(func.count()).select_from(PunchRawEvent)), 1)

    async def test_late_absence_and_approved_leave(self):
        first_id, second_id, third_id, course_id, _ = await self.seed()
        event = self.event("late", f"{self.day.isoformat()}T18:36:00+08:00", "A1111111")
        async with self.sessions() as db:
            results = await ingest_events(db, [event])
            await db.commit()
            self.assertEqual(results[0]["attendance_status"], "late")
            record = (
                await db.execute(
                    select(ClassAttendance).where(ClassAttendance.student_id == first_id)
                )
            ).scalar_one()
            self.assertEqual(record.late_minutes, 6)
        async with self.sessions() as db:
            rows = await get_class_attendance(db, self.day, self.day, student_id=second_id, course_id=course_id)
            await db.commit()
            self.assertEqual(rows[0]["status"], "absent")
        async with self.sessions() as db:
            db.add(
                LeaveApplication(
                    student_id=third_id,
                    course_id=course_id,
                    leave_date=self.day,
                    leave_type="sick",
                    status="approved",
                )
            )
            await db.commit()
            rows = await get_class_attendance(db, self.day, self.day, student_id=third_id, course_id=course_id)
            await db.commit()
            self.assertEqual(rows[0]["status"], "leave")
            self.assertEqual(rows[0]["leave_type"], "sick")

    async def test_adjacent_classes_map_one_event_to_one_class(self):
        first_id, _, _, first_course_id, second_course_id = await self.seed()
        event = self.event("boundary", f"{self.day.isoformat()}T19:30:00+08:00", "A1111111")
        async with self.sessions() as db:
            results = await ingest_events(db, [event])
            await db.commit()
            self.assertEqual(results[0]["course_id"], second_course_id)
            records = (
                await db.execute(
                    select(ClassAttendance).where(
                        ClassAttendance.student_id == first_id,
                        ClassAttendance.attendance_date == self.day,
                    )
                )
            ).scalars().all()
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0].course_id, second_course_id)
            self.assertEqual(records[0].punch_count, 1)
            self.assertNotEqual(records[0].course_id, first_course_id)

    async def test_abnormal_event_does_not_create_class_attendance(self):
        _, _, third_id, _, _ = await self.seed()
        event = self.event("m24", f"{self.day.isoformat()}T18:45:00+08:00", "A3333333", code="M24")
        async with self.sessions() as db:
            results = await ingest_events(db, [event])
            await db.commit()
            self.assertEqual(results[0]["status"], "ok")
            self.assertEqual(results[0]["attendance_status"], "unmatched")
            self.assertEqual(
                await db.scalar(
                    select(func.count())
                    .select_from(ClassAttendance)
                    .where(ClassAttendance.student_id == third_id)
                ),
                0,
            )

    async def test_makeup_class_and_unknown_card_are_stored(self):
        _, second_id, _, course_id, _ = await self.seed()
        makeup_day = self.day + timedelta(days=1)
        async with self.sessions() as db:
            db.add(
                MakeupClass(
                    student_id=second_id,
                    course_id=course_id,
                    makeup_date=makeup_day,
                    start_time=time(18, 0),
                    end_time=time(19, 0),
                    status="scheduled",
                )
            )
            await db.commit()
        async with self.sessions() as db:
            results = await ingest_events(
                db,
                [self.event("makeup", f"{makeup_day.isoformat()}T18:00:00+08:00", "A2222222")],
            )
            await db.commit()
            self.assertEqual(results[0]["session_type"], "makeup")
        async with self.sessions() as db:
            results = await ingest_events(
                db,
                [self.event("unknown", f"{self.day.isoformat()}T18:00:00+08:00", "A9999999")],
            )
            await db.commit()
            self.assertEqual(results[0]["status"], "unknown_card")
            self.assertTrue(results[0]["stored"])
            self.assertEqual(await db.scalar(select(func.count()).select_from(PunchRawEvent)), 2)


if __name__ == "__main__":
    unittest.main()
