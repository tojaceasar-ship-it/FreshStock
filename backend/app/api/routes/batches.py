from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from datetime import date, datetime
from app.core.database import get_db
from app.core.deps import get_current_user, require_permission
from app.models.batch import Batch
from app.models.product import Product
from pydantic import BaseModel, ConfigDict
from decimal import Decimal

router = APIRouter()

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
    product_sku: Optional[str] = None
    product_ean: Optional[str] = None
    product_unit: Optional[str] = None
    days_until_expiry: Optional[int] = None
    model_config = ConfigDict(from_attributes=True)

@router.get("", response_model=List[BatchOut])
def list_batches(
    product_id: Optional[int] = None,
    expiring_in_days: Optional[int] = None,
    expired: Optional[bool] = None,
    location_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user = Depends(require_permission("inventory:read"))
):
    q = db.query(Batch).join(Product, Batch.product_id == Product.id)
    
    if product_id:
        q = q.filter(Batch.product_id == product_id)
    if location_id:
        q = q.filter(Batch.warehouse_location_id == location_id)
    if expired:
        q = q.filter(Batch.expiry_date < date.today(), Batch.quantity_available > 0)
    if expiring_in_days is not None:
        from datetime import timedelta
        threshold = date.today() + timedelta(days=expiring_in_days)
        q = q.filter(Batch.expiry_date <= threshold, Batch.expiry_date >= date.today(), Batch.quantity_available > 0)
    
    q = q.order_by(Batch.expiry_date.asc().nulls_last())
    batches = q.all()
    
    result = []
    today = date.today()
    for b in batches:
        out = BatchOut.model_validate(b)
        prod = db.query(Product).filter(Product.id == b.product_id).first()
        if prod:
            out.product_name = prod.name
            out.product_sku = prod.sku
            out.product_ean = prod.ean
            out.product_unit = prod.unit.value if hasattr(prod.unit, "value") else str(prod.unit)
        if b.expiry_date:
            out.days_until_expiry = (b.expiry_date - today).days
        result.append(out)
    return result

@router.get("/expiry/overview")
def expiry_overview(db: Session = Depends(get_db), current_user = Depends(require_permission("inventory:read"))):
    today = date.today()
    from datetime import timedelta

    def in_window(lower_days, upper_days):
        """Batches expiring after `lower_days` and on/before `upper_days` from today."""
        lower = today + timedelta(days=lower_days)
        upper = today + timedelta(days=upper_days)
        return (
            Batch.expiry_date > lower,
            Batch.expiry_date <= upper,
            Batch.quantity_available > 0,
        )

    expired = (Batch.expiry_date < today, Batch.quantity_available > 0)
    windows = {
        "expired": expired,
        "today": (Batch.expiry_date == today, Batch.quantity_available > 0),
        "1_day": in_window(0, 1),
        "3_days": in_window(1, 3),
        "7_days": in_window(3, 7),
        "14_days": in_window(7, 14),
        "30_days": in_window(14, 30),
    }

    def tally(*conditions):
        rows = db.query(
            func.count(Batch.id),
            func.coalesce(func.sum(Batch.quantity_available), 0),
            func.coalesce(func.sum(Batch.quantity_available * Batch.purchase_price), 0),
        ).filter(*conditions).one()
        return int(rows[0]), rows[1], float(rows[2] or 0)

    # `buckets` stays a flat {name: quantity_at_risk} map for the existing UI.
    counts, details, totals = {}, {}, {}
    for name, conditions in windows.items():
        batch_count, quantity, value = tally(*conditions)
        counts[name] = quantity
        details[name] = {"batch_count": batch_count, "quantity": quantity, "total_value": value}

    _, expired_quantity, expired_value = tally(*expired)

    return {
        "buckets": counts,
        "bucket_details": details,
        "expired_quantity": expired_quantity,
        "expired_value": expired_value,
    }

@router.get("/{batch_id}", response_model=BatchOut)
def get_batch(batch_id: int, db: Session = Depends(get_db), current_user = Depends(require_permission("inventory:read"))):
    b = db.query(Batch).filter(Batch.id == batch_id).first()
    if not b:
        raise HTTPException(status_code=404, detail="Not found")
    out = BatchOut.model_validate(b)
    prod = db.query(Product).filter(Product.id == b.product_id).first()
    if prod:
        out.product_name = prod.name
        out.product_sku = prod.sku
        out.product_ean = prod.ean
        out.product_unit = prod.unit.value if hasattr(prod.unit, "value") else str(prod.unit)
    if b.expiry_date:
        out.days_until_expiry = (b.expiry_date - date.today()).days
    return out
