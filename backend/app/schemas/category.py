from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Optional
from datetime import datetime

class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: Optional[str] = None
    parent_id: Optional[int] = None
    color: Optional[str] = "#6B7280"

    @field_validator("name")
    @classmethod
    def nonblank_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Nazwa kategorii nie może być pusta")
        return value

class CategoryUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    parent_id: Optional[int] = None
    color: Optional[str] = None

    @field_validator("name")
    @classmethod
    def nonblank_name(cls, value: Optional[str]) -> Optional[str]:
        return CategoryCreate.nonblank_name(value) if value is not None else None

class CategoryOut(BaseModel):
    id: int
    name: str
    description: Optional[str]
    parent_id: Optional[int]
    color: str
    created_at: datetime
    product_count: Optional[int] = 0
    
    model_config = ConfigDict(from_attributes=True)
