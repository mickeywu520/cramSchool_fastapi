"""Common response schemas."""

from typing import Any

from pydantic import BaseModel


class SuccessResponse(BaseModel):
    success: bool = True
    data: Any = None
    message: str = "操作成功"


class ErrorDetail(BaseModel):
    field: str | None = None
    reason: str


class ErrorResponse(BaseModel):
    success: bool = False
    error: dict


class PaginatedResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[Any]