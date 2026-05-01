"""About Card schemas."""

from pydantic import BaseModel


class AboutCardResponse(BaseModel):
    id: int
    title: str
    content: str
    icon: str | None = None
    display_order: int = 0
    is_active: bool = True

    model_config = {"from_attributes": True}


class AboutCardListResponse(BaseModel):
    total: int
    cards: list[AboutCardResponse]


class AboutCardCreateRequest(BaseModel):
    title: str
    content: str
    icon: str | None = None
    display_order: int = 0
    is_active: bool = True


class AboutCardUpdateRequest(BaseModel):
    title: str | None = None
    content: str | None = None
    icon: str | None = None
    display_order: int | None = None
    is_active: bool | None = None


class AboutCardReorderRequest(BaseModel):
    order: list[int]