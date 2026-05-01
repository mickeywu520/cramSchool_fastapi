"""Banner schemas."""

from pydantic import BaseModel


class BannerResponse(BaseModel):
    id: int
    title: str | None = None
    image_url: str
    link_url: str | None = None
    display_order: int = 0
    is_active: bool = True

    model_config = {"from_attributes": True}


class BannerCreateRequest(BaseModel):
    title: str | None = None
    image_url: str
    link_url: str | None = None
    display_order: int = 0
    is_active: bool = True


class BannerUpdateRequest(BaseModel):
    title: str | None = None
    image_url: str | None = None
    link_url: str | None = None
    display_order: int | None = None
    is_active: bool | None = None


class BannerReorderRequest(BaseModel):
    order: list[int]
