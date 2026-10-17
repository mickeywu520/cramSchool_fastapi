"""Parent/student account management.

List and permanently delete parent / student login accounts.

帳號類型（兩者 role 都是 "student"，靠 auth_provider 區分）：
- parent  ：auth_provider == "email"，學生關聯在 students.parent_user_id
- student ：auth_provider == "id_number"，學生關聯在 students.user_id（帳號＝密碼＝身分證字號）

刪除為不可逆的硬刪除：帳號 + 依附學生 + 所有子表。刪除前若任一學生仍有
status == "active" 的選課，會擋下並回傳課程清單（guard 必須在後端執行）。
"""

from fastapi import status
from sqlalchemy import delete, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.attendance import AttendanceDaily, ClassAttendance, PunchRawEvent
from app.models.communication import CommunicationBookEntry
from app.models.communication_session import CommunicationSessionStudent
from app.models.course import Course
from app.models.enrollment import Enrollment
from app.models.exam_score import ExamScore
from app.models.homework import HomeworkRecord
from app.models.leave import LeaveApplication
from app.models.makeup import MakeupClass
from app.models.parent_feedback import ParentFeedback
from app.models.password_reset_token import PasswordResetToken
from app.models.refresh_token import RefreshToken
from app.models.reminder import Reminder
from app.models.student import Student
from app.models.user import User
from app.utils.exceptions import AppException, NotFoundException


def _account_type(user: User) -> str:
    return "student" if user.auth_provider == "id_number" else "parent"


async def list_accounts(
    db: AsyncSession,
    account_type: str | None = None,
    search: str | None = None,
) -> list[dict]:
    users = (
        await db.execute(
            select(User).where(User.role == "student").order_by(User.created_at.desc())
        )
    ).scalars().all()
    if not users:
        return []

    user_ids = {u.id for u in users}
    students = (
        await db.execute(
            select(Student)
            .where(or_(Student.user_id.in_(user_ids), Student.parent_user_id.in_(user_ids)))
            .options(selectinload(Student.enrollments).selectinload(Enrollment.course))
        )
    ).scalars().all()

    by_account: dict[int, list[Student]] = {uid: [] for uid in user_ids}
    for s in students:
        if s.user_id in by_account:
            by_account[s.user_id].append(s)  # type: ignore[index]
        if s.parent_user_id in by_account:
            by_account[s.parent_user_id].append(s)  # type: ignore[index]

    term = (search or "").strip().lower()
    items: list[dict] = []
    for u in users:
        atype = _account_type(u)
        if account_type and atype != account_type:
            continue

        attached = by_account.get(u.id, [])
        briefs = []
        for s in attached:
            active_courses = [
                e.course.name
                for e in s.enrollments
                if e.status == "active" and e.course is not None
            ]
            briefs.append(
                {
                    "id": s.id,
                    "student_name": s.student_name,
                    "id_number": s.id_number,
                    "grade": s.grade,
                    "followup_status": s.followup_status,
                    "active_course_count": len(active_courses),
                    "active_courses": active_courses,
                }
            )

        if atype == "student":
            login_id = attached[0].id_number or "" if attached else ""
            display_name = attached[0].student_name if attached else ""
        else:
            login_id = u.email or u.username or ""
            display_name = (attached[0].parent_name if attached else "") or login_id

        if term:
            haystack = " ".join(
                [
                    login_id,
                    display_name,
                    u.email or "",
                    u.username or "",
                    *[b["student_name"] for b in briefs],
                    *[b["id_number"] or "" for b in briefs],
                ]
            ).lower()
            if term not in haystack:
                continue

        items.append(
            {
                "id": u.id,
                "account_type": atype,
                "login_id": login_id,
                "display_name": display_name,
                "username": u.username,
                "is_active": u.is_active,
                "last_login_at": u.last_login_at,
                "created_at": u.created_at,
                "students": briefs,
            }
        )
    return items


async def delete_account(db: AsyncSession, user_id: int) -> dict:
    user = await db.get(User, user_id)
    if user is None or user.role != "student":
        raise NotFoundException("Account")

    students = (
        await db.execute(
            select(Student).where(
                or_(Student.user_id == user_id, Student.parent_user_id == user_id)
            )
        )
    ).scalars().all()

    # Guard: 學生仍在課程中（status == "active"）→ 擋下並附課程清單。
    conflicts: list[dict] = []
    for s in students:
        rows = (
            await db.execute(
                select(Course.name)
                .join(Enrollment, Enrollment.course_id == Course.id)
                .where(Enrollment.student_id == s.id, Enrollment.status == "active")
            )
        ).all()
        if rows:
            conflicts.append(
                {
                    "student_id": s.id,
                    "student_name": s.student_name,
                    "courses": [r[0] for r in rows],
                }
            )
    if conflicts:
        raise AppException(
            status.HTTP_409_CONFLICT,
            "STUDENT_STILL_ENROLLED",
            "學生仍在課程中，請先將學生移出課程後再刪除帳號",
            conflicts,
        )

    student_ids = [s.id for s in students]
    # 被刪學生的專屬身分證帳號（students.user_id）；刪完學生後若無其他學生依附即一併刪除
    linked_user_ids = {s.user_id for s in students if s.user_id is not None}

    if student_ids:
        # 聯絡簿子表 → 聯絡簿主表（homework / reminder / parent_feedback 參照主表）
        entry_ids = (
            await db.execute(
                select(CommunicationBookEntry.id).where(
                    CommunicationBookEntry.student_id.in_(student_ids)
                )
            )
        ).scalars().all()
        if entry_ids:
            await db.execute(
                delete(ParentFeedback).where(
                    ParentFeedback.communication_book_id.in_(entry_ids)
                )
            )
            await db.execute(
                delete(Reminder).where(Reminder.communication_book_id.in_(entry_ids))
            )
            await db.execute(
                delete(HomeworkRecord).where(
                    HomeworkRecord.communication_book_id.in_(entry_ids)
                )
            )
            await db.execute(
                delete(CommunicationBookEntry).where(
                    CommunicationBookEntry.id.in_(entry_ids)
                )
            )

        await db.execute(
            delete(CommunicationSessionStudent).where(
                CommunicationSessionStudent.student_id.in_(student_ids)
            )
        )
        await db.execute(delete(ExamScore).where(ExamScore.student_id.in_(student_ids)))

        # 先解除 punch_raw_events 對 class_attendance 的參照，再刪 class_attendance
        ca_ids = (
            await db.execute(
                select(ClassAttendance.id).where(
                    ClassAttendance.student_id.in_(student_ids)
                )
            )
        ).scalars().all()
        if ca_ids:
            await db.execute(
                update(PunchRawEvent)
                .where(PunchRawEvent.class_attendance_id.in_(ca_ids))
                .values(class_attendance_id=None)
            )
        await db.execute(
            delete(ClassAttendance).where(ClassAttendance.student_id.in_(student_ids))
        )

        # class_attendance.leave_id 參照 leave_applications：先刪 class_attendance 再刪請假
        await db.execute(
            delete(LeaveApplication).where(LeaveApplication.student_id.in_(student_ids))
        )
        await db.execute(delete(MakeupClass).where(MakeupClass.student_id.in_(student_ids)))

        # 打卡原始紀錄保留稽核，但解除學生關聯
        await db.execute(
            update(PunchRawEvent)
            .where(PunchRawEvent.student_id.in_(student_ids))
            .values(student_id=None)
        )
        await db.execute(
            delete(AttendanceDaily).where(AttendanceDaily.student_id.in_(student_ids))
        )
        await db.execute(
            delete(Enrollment).where(Enrollment.student_id.in_(student_ids))
        )
        await db.execute(delete(Student).where(Student.id.in_(student_ids)))

        # 清掉因學生被刪而無依附學生的身分證帳號，避免列表出現空帳號列。
        # 仍被其他同身分證學生共用者保留。
        for uid in linked_user_ids:
            if uid == user_id:
                continue
            remaining = (
                await db.execute(
                    select(Student.id).where(Student.user_id == uid).limit(1)
                )
            ).scalar_one_or_none()
            if remaining is None:
                await db.execute(delete(RefreshToken).where(RefreshToken.user_id == uid))
                await db.execute(
                    delete(PasswordResetToken).where(PasswordResetToken.user_id == uid)
                )
                await db.execute(delete(User).where(User.id == uid))

    await db.execute(delete(RefreshToken).where(RefreshToken.user_id == user_id))
    await db.execute(
        delete(PasswordResetToken).where(PasswordResetToken.user_id == user_id)
    )
    await db.execute(delete(User).where(User.id == user_id))
    await db.flush()

    return {
        "success": True,
        "deleted_students": len(student_ids),
        "message": f"已刪除帳號與 {len(student_ids)} 位學生",
    }
