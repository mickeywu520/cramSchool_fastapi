"""Branch schemas."""

from pydantic import BaseModel, Field


class BranchResponse(BaseModel):
    id: int
    name: str
    phone: str | None = None
    address: str | None = None
    is_active: bool = True
    display_order: int = 0

    model_config = {"from_attributes": True}


class BranchCreateRequest(BaseModel):
    name: str = Field(..., max_length=50)
    phone: str | None = Field(None, max_length=20)
    address: str | None = Field(None, max_length=200)
    is_active: bool = True
    display_order: int = 0


class BranchUpdateRequest(BaseModel):
    name: str | None = Field(None, max_length=50)
    phone: str | None = Field(None, max_length=20)
    address: str | None = Field(None, max_length=200)
    is_active: bool | None = None
    display_order: int | None = None
