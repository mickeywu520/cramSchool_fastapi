"""Honor roll schemas."""

from pydantic import BaseModel


class HonorResponse(BaseModel):
    id: int
    student_name: str
    school: str
    department: str | None = None
    year: int
    exam_type: str | None = None
    display_order: int = 0

    model_config = {"from_attributes": True}


class HonorListResponse(BaseModel):
    total: int
    honors: list[HonorResponse]