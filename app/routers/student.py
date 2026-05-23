"""Student router - profile, progress, courses, exams, homework."""

import os
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.middleware.auth_middleware import require_student
from app.models.student import Student
from app.models.user import User
from app.schemas.student import (
    CourseSummary,
    ExamScoreResponse,
    HomeworkSummary,
    ProgressResponse,
    StudentResponse,
    StudentUpdateRequest,
)
from app.services import student_service

router = APIRouter(prefix="/student", tags=["Student"])

ALLOWED_AVATAR_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_AVATAR_SIZE = 5 * 1024 * 1024


@router.get("/me", response_model=StudentResponse)
async def get_my_profile(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_student),
):
    return await student_service.get_student_response(db, current_user.id)


@router.put("/me", response_model=StudentResponse)
async def update_my_profile(
    data: StudentUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_student),
):
    result = await student_service.update_student(db, current_user.id, data.model_dump(exclude_none=True))
    await db.commit()
    return result


@router.get("/progress", response_model=ProgressResponse)
async def get_my_progress(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_student),
):
    return await student_service.get_progress(db, current_user.id)


@router.get("/courses", response_model=list[CourseSummary])
async def get_my_courses(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_student),
):
    return await student_service.get_my_courses(db, current_user.id)


@router.get("/exams", response_model=list[ExamScoreResponse])
async def get_my_exams(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_student),
):
    return await student_service.get_my_exams(db, current_user.id)


@router.get("/homework", response_model=list[HomeworkSummary])
async def get_my_homework(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_student),
):
    return await student_service.get_my_homework(db, current_user.id)


@router.post("/avatar")
async def upload_avatar(
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_student),
):
    if file.content_type not in ALLOWED_AVATAR_TYPES:
        raise HTTPException(status_code=400, detail="不支援的檔案格式，請使用 JPEG, PNG, WebP, GIF")
    contents = await file.read()
    if len(contents) > MAX_AVATAR_SIZE:
        raise HTTPException(status_code=400, detail="檔案大小不可超過 5MB")
    ext = file.filename.split(".")[-1] if "." in file.filename else "jpg"
    filename = f"{uuid.uuid4()}.{ext}"
    upload_path = Path(settings.UPLOAD_DIR) / "avatars"
    upload_path.mkdir(parents=True, exist_ok=True)
    file_path = upload_path / filename
    with open(file_path, "wb") as f:
        f.write(contents)
    base_url = str(request.base_url).rstrip("/").replace("http://", "https://")
    avatar_url = f"{base_url}/uploads/avatars/{filename}"
    result = await db.execute(
        select(Student).where(Student.user_id == current_user.id)
    )
    student = result.scalar_one_or_none()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    student.avatar_url = avatar_url
    await db.commit()
    return {"success": True, "url": avatar_url, "message": "頭像更新成功"}