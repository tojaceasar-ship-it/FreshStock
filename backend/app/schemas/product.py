from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Optional, List
from datetime import datetime, date
from decimal import Decimal

class ProductCreate(BaseModel):
    sku: str = Field(min_length=1, max_length=100)
    ean: Optional[str] = Field(None, max_length=50)
    name: str = Field(min_length=1, max_length=255)
    brand: Optional[str] = None
    description: Optional[str] = None
    category_id: Optional[int] = None
    unit: str = "szt"
    vat_rate: Decimal = Decimal("23.00")
    purchase_price: Decimal = Field(ge=0)
    selling_price: Decimal = Field(ge=0)
    min_stock: Decimal = Field(default=Decimal("5"), ge=0, max_digits=14, decimal_places=3)
    target_stock: Decimal = Field(default=Decimal("20"), ge=0, max_digits=14, decimal_places=3)
    safety_stock: Decimal = Field(default=Decimal("3"), ge=0, max_digits=14, decimal_places=3)
    is_active: bool = True
    default_supplier_id: Optional[int] = None
    image_url: Optional[str] = None
    requires_expiry_control: bool = True
    expiry_warning_days: int = 7

    @field_validator("sku", "name")
    @classmethod
    def nonblank_identity(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Pole nie może być puste")
        return value

class ProductUpdate(BaseModel):
    sku: Optional[str] = Field(None, min_length=1, max_length=100)
    ean: Optional[str] = Field(None, max_length=50)
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    brand: Optional[str] = None
    description: Optional[str] = None
    category_id: Optional[int] = None
    unit: Optional[str] = None
    vat_rate: Optional[Decimal] = None
    purchase_price: Optional[Decimal] = Field(None, ge=0)
    selling_price: Optional[Decimal] = Field(None, ge=0)
    min_stock: Optional[Decimal] = Field(None, ge=0, max_digits=14, decimal_places=3)
    target_stock: Optional[Decimal] = Field(None, ge=0, max_digits=14, decimal_places=3)
    safety_stock: Optional[Decimal] = Field(None, ge=0, max_digits=14, decimal_places=3)
    is_active: Optional[bool] = None
    default_supplier_id: Optional[int] = None
    image_url: Optional[str] = None
    requires_expiry_control: Optional[bool] = None
    expiry_warning_days: Optional[int] = None

    @field_validator("sku", "name")
    @classmethod
    def nonblank_identity(cls, value: Optional[str]) -> Optional[str]:
        return ProductCreate.nonblank_identity(value) if value is not None else None

class ProductOut(BaseModel):
    id: int
    sku: str
    ean: Optional[str]
    name: str
    brand: Optional[str]
    description: Optional[str]
    category_id: Optional[int]
    unit: str
    vat_rate: Decimal
    purchase_price: Decimal
    selling_price: Decimal
    min_stock: Decimal
    target_stock: Decimal
    safety_stock: Decimal
    is_active: bool
    default_supplier_id: Optional[int]
    image_url: Optional[str]
    requires_expiry_control: bool
    expiry_warning_days: int
    created_at: datetime
    updated_at: Optional[datetime]
    # computed
    total_stock: Optional[Decimal] = Decimal("0")
    category_name: Optional[str] = None
    
    model_config = ConfigDict(from_attributes=True)

class BatchCreate(BaseModel):
    product_id: int
    batch_number: str
    expiry_date: Optional[date] = None
    manufacture_date: Optional[date] = None
    quantity_received: Decimal = Field(ge=0, max_digits=14, decimal_places=3)
    purchase_price: Optional[Decimal] = None
    supplier_id: Optional[int] = None
    delivery_id: Optional[int] = None
    warehouse_location_id: Optional[int] = None

class BatchOut(BaseModel):
    id: int
    product_id: int
    batch_number: str
    expiry_date: Optional[date]
    manufacture_date: Optional[date]
    quantity_received: Decimal
    quantity_available: Decimal
    purchase_price: Optional[Decimal]
    supplier_id: Optional[int]
    delivery_id: Optional[int]
    warehouse_location_id: Optional[int]
    created_at: datetime
    product_name: Optional[str] = None
    days_until_expiry: Optional[int] = None
    
    model_config = ConfigDict(from_attributes=True)

class StockOut(BaseModel):
    id: int
    product_id: int
    location_id: int
    quantity: Decimal
    product_name: Optional[str] = None
    location_name: Optional[str] = None
    
    model_config = ConfigDict(from_attributes=True)
