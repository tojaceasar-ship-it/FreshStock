from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class EventType(str, Enum):
    SALE = "SALE"
    REFUND = "REFUND"
    VOID = "VOID"
    PRODUCT_CREATED = "PRODUCT_CREATED"
    PRODUCT_UPDATED = "PRODUCT_UPDATED"
    PRICE_CHANGED = "PRICE_CHANGED"
    STOCK_UPDATED = "STOCK_UPDATED"


class NormalizedItem(BaseModel):
    external_product_id: str = Field(min_length=1, max_length=255)
    ean: Optional[str] = Field(None, max_length=50)
    sku: Optional[str] = Field(None, max_length=100)
    name: Optional[str] = Field(None, max_length=255)
    quantity: Decimal = Field(gt=0)
    unit_price: Decimal = Field(ge=0)
    total: Decimal = Field(ge=0)


class NormalizedEvent(BaseModel):
    event_type: EventType
    provider: str = Field(min_length=1, max_length=50)
    external_event_id: str = Field(min_length=1, max_length=255)
    external_transaction_id: str = Field(min_length=1, max_length=255)
    location_external_id: Optional[str] = Field(None, max_length=255)
    timestamp: datetime
    currency: str = Field(default="PLN", min_length=3, max_length=3)
    items: List[NormalizedItem] = Field(min_length=1)
    raw: Optional[Dict[str, Any]] = None

    @field_validator("currency")
    @classmethod
    def uppercase_currency(cls, value: str) -> str:
        return value.upper()


class IntegrationCreate(BaseModel):
    provider: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=255)
    sync_mode: str = "CSV"
    external_merchant_id: Optional[str] = None
    external_location_id: Optional[str] = None
    credentials: Optional[Dict[str, Any]] = None
    settings: Optional[Dict[str, Any]] = None


class IntegrationUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    status: Optional[str] = None
    sync_mode: Optional[str] = None
    external_merchant_id: Optional[str] = None
    external_location_id: Optional[str] = None
    credentials: Optional[Dict[str, Any]] = None
    settings: Optional[Dict[str, Any]] = None


class IntegrationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    provider: str
    name: str
    status: str
    sync_mode: str
    external_merchant_id: Optional[str]
    external_location_id: Optional[str]
    last_sync_at: Optional[datetime]
    last_success_at: Optional[datetime]
    last_error_at: Optional[datetime]
    created_at: datetime
    capabilities: Dict[str, bool] = Field(default_factory=dict)
    mapped_products: int = 0
    unmapped_products: int = 0
    error_count: int = 0
    sales_today_count: int = 0
    sales_today_amount: float = 0

class MappingCreate(BaseModel):
    external_product_id: str = Field(min_length=1, max_length=255)
    freshstock_product_id: int
    ean: Optional[str] = None
    sku: Optional[str] = None
    mapping_method: str = "MANUAL"


class MappingUpdate(BaseModel):
    """PATCH body for a product mapping.

    Every field is optional so a caller can correct one attribute without
    resending the whole mapping. Omitted fields keep their stored value.
    """

    freshstock_product_id: Optional[int] = None
    ean: Optional[str] = None
    sku: Optional[str] = None


class ResolveReturnRequest(BaseModel):
    action: str
    batch_id: Optional[int] = None
    reason: Optional[str] = None


class BridgeRegisterRequest(BaseModel):
    integration_id: int
    store_id: str = Field(min_length=1, max_length=100)
    version: Optional[str] = Field(None, max_length=50)


class BridgeHeartbeatRequest(BaseModel):
    version: Optional[str] = Field(None, max_length=50)


class CSVColumnMapping(BaseModel):
    date: Optional[str] = None
    time: Optional[str] = None
    transaction_id: str
    ean: Optional[str] = None
    sku: Optional[str] = None
    external_product_id: Optional[str] = None
    name: Optional[str] = None
    quantity: str
    unit_price: str
    total: Optional[str] = None
    location: Optional[str] = None

    @field_validator("transaction_id", "quantity", "unit_price")
    @classmethod
    def required_column_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Nazwa wymaganej kolumny nie może być pusta")
        return value.strip()
