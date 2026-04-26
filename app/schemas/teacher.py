"""Teacher schemas."""

from pydantic import BaseModel


class TeacherResponse(BaseModel):
    id: int
    name: str
    subject: str
    title: str | None = None
    motto: str | None = None
    description: str | None = None
    photo_url: str | None = None
    life_photo_url: str | None = None
    display_order: int = 0
    is_active: bool = True

    model_config = {"from_attributes": True}


class TeacherListResponse(BaseModel):
    total: int
    teachers: list[TeacherResponse]