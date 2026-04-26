"""Course schemas."""

from pydantic import BaseModel


class CourseResponse(BaseModel):
    id: int
    name: str
    category: str
    subject: str
    teacher_id: int | None = None
    teacher_name: str | None = None
    description: str | None = None
    schedule: str | None = None
    price: int | None = None
    max_students: int | None = None
    is_early_bird: bool = False
    early_bird_discount: str | None = None
    is_active: bool = True
    display_order: int = 0

    model_config = {"from_attributes": True}


class CourseListResponse(BaseModel):
    total: int
    courses: list[CourseResponse]