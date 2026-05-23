"""Course schemas."""

from datetime import date
from pydantic import BaseModel, Field


class CourseResponse(BaseModel):
    id: int
    name: str
    category: str
    subject: str
    teacher_id: int | None = None
    teacher_name: str | None = None
    description: str | None = None
    schedule: str | None = None
    grade_level: str | None = None
    day_of_week: int | None = None
    start_time: str | None = None
    end_time: str | None = None
    location: str | None = None
    school_year: str | None = None
    semester: str | None = None
    price: int | None = None
    max_students: int | None = None
    is_early_bird: bool = False
    early_bird_discount: str | None = None
    is_active: bool = True
    display_order: int = 0

    model_config = {"from_attributes": True}


class CourseCreateRequest(BaseModel):
    name: str = Field(..., max_length=100)
    category: str = Field(..., max_length=20)
    subject: str = Field(..., max_length=20)
    teacher_id: int | None = None
    description: str | None = None
    schedule: str | None = None
    grade_level: str | None = Field(None, max_length=20)
    day_of_week: int | None = None
    start_time: str | None = Field(None, max_length=10)
    end_time: str | None = Field(None, max_length=10)
    location: str | None = Field(None, max_length=50)
    school_year: str | None = Field(None, max_length=10)
    semester: str | None = Field(None, max_length=10)
    price: int | None = None
    max_students: int | None = None
    is_early_bird: bool = False
    early_bird_discount: str | None = None
    is_active: bool = True
    display_order: int = 0


class CourseUpdateRequest(BaseModel):
    name: str | None = Field(None, max_length=100)
    category: str | None = Field(None, max_length=20)
    subject: str | None = Field(None, max_length=20)
    teacher_id: int | None = None
    description: str | None = None
    schedule: str | None = None
    grade_level: str | None = Field(None, max_length=20)
    day_of_week: int | None = None
    start_time: str | None = Field(None, max_length=10)
    end_time: str | None = Field(None, max_length=10)
    location: str | None = Field(None, max_length=50)
    school_year: str | None = Field(None, max_length=10)
    semester: str | None = Field(None, max_length=10)
    price: int | None = None
    max_students: int | None = None
    is_early_bird: bool | None = None
    early_bird_discount: str | None = None
    is_active: bool | None = None
    display_order: int | None = None


class CourseListResponse(BaseModel):
    total: int
    courses: list[CourseResponse]


class EnrollmentResponse(BaseModel):
    id: int
    student_id: int
    student_name: str
    course_id: int
    course_name: str
    status: str
    enrolled_at: str | None = None

    model_config = {"from_attributes": True}


class EnrollmentCreateRequest(BaseModel):
    student_id: int
    course_id: int
