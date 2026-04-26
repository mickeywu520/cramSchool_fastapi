"""Announcement schemas."""

from datetime import datetime
from pydantic import BaseModel


class AnnouncementResponse(BaseModel):
    id: int
    title: str
    content: str
    priority: str = "normal"
    target_role: str = "all"
    is_published: bool = True
    published_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AnnouncementCreateRequest(BaseModel):
    title: str
    content: str
    priority: str = "normal"
    target_role: str = "all"
    is_published: bool = True