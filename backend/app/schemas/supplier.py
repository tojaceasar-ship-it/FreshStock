from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Optional
from datetime import datetime
from decimal import Decimal

class SupplierCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    address: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    vat_number: Optional[str] = None
    contact_person: Optional[str] = None
    payment_terms: Optional[str] = "14 dni"
    min_order_value: Decimal = Decimal("0")
    lead_time_days: int = 2
    is_active: bool = True
    notes: Optional[str] = None

    @field_validator("name")
    @classmethod
    def nonblank_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Nazwa dostawcy nie może być pusta")
        return value

class SupplierUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    address: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    vat_number: Optional[str] = None
    contact_person: Optional[str] = None
    payment_terms: Optional[str] = None
    min_order_value: Optional[Decimal] = None
    lead_time_days: Optional[int] = None
    is_active: Optional[bool] = None
    notes: Optional[str] = None

    @field_validator("name")
    @classmethod
    def nonblank_name(cls, value: Optional[str]) -> Optional[str]:
        return SupplierCreate.nonblank_name(value) if value is not None else None

class SupplierOut(BaseModel):
    id: int
    name: str
    address: Optional[str]
    email: Optional[str]
    phone: Optional[str]
    vat_number: Optional[str]
    contact_person: Optional[str]
    payment_terms: Optional[str]
    min_order_value: Decimal
    lead_time_days: int
    is_active: bool
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)
