"""File upload router for images."""

import os
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.middleware.auth_middleware import require_teacher_or_admin
from app.models.user import User

router = APIRouter(prefix="/upload", tags=["Upload"])

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_FILE_SIZE = 10 * 1024 * 1024

UPLOAD_DIRS = {
    "avatars": "avatars",
    "teachers": "teachers",
    "banners": "banners",
    "honors": "honors",
    "general": "general",
}


@router.post("/image/{category}")
async def upload_image(
    category: str,
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_teacher_or_admin),
):
    if category not in UPLOAD_DIRS:
        raise HTTPException(
            status_code=400,
            detail=f"不支援的分類: {category}。支援: {list(UPLOAD_DIRS.keys())}",
        )
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"不支援的檔案格式: {file.content_type}。支援: JPEG, PNG, WebP, GIF",
        )
    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="檔案大小不可超過 10MB")
    ext = file.filename.split(".")[-1] if "." in file.filename else "jpg"
    filename = f"{uuid.uuid4()}.{ext}"
    subdir = UPLOAD_DIRS[category]
    upload_path = Path(settings.UPLOAD_DIR) / subdir
    upload_path.mkdir(parents=True, exist_ok=True)
    file_path = upload_path / filename
    with open(file_path, "wb") as f:
        f.write(contents)
    base_url = str(request.base_url).rstrip("/").replace("http://", "https://")
    full_url = f"{base_url}/uploads/{subdir}/{filename}"
    return {
        "success": True,
        "url": full_url,
        "filename": filename,
        "message": "上傳成功",
    }