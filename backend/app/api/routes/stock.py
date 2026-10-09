from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from app.core.database import get_db
from app.core.deps import get_current_user, require_permission
from app.models.stock import Stock
from app.models.batch import Batch
from app.models.product import Product
from app.models.location import WarehouseLocation
from pydantic import BaseModel, ConfigDict
from datetime import datetime
from decimal import Decimal

router = APIRouter()

class StockOut(BaseModel):
    id: int
    product_id: int
    location_id: int
    quantity: Decimal
    product_name: str
    product_sku: str
    location_name: str
    updated_at: Optional[datetime]
    model_config = ConfigDict(from_attributes=True)

class StockSummary(BaseModel):
    product_id: int
    product_name: str
    product_sku: str
    total_quantity: Decimal
    locations: List[dict]

@router.get("", response_model=List[StockOut])
def list_stock(product_id: Optional[int] = None, location_id: Optional[int] = None, db: Session = Depends(get_db), current_user = Depends(require_permission("stock:read"))):
    q = db.query(Stock).join(Product, Stock.product_id == Product.id).join(WarehouseLocation, Stock.location_id == WarehouseLocation.id)
    if product_id:
        q = q.filter(Stock.product_id == product_id)
    if location_id:
        q = q.filter(Stock.location_id == location_id)
    stocks = q.all()
    result = []
    for s in stocks:
        result.append(StockOut(
            id=s.id,
            product_id=s.product_id,
            location_id=s.location_id,
            quantity=s.quantity,
            product_name=s.product.name if s.product else "Unknown",
            product_sku=s.product.sku if s.product else "",
            location_name=s.location.name if s.location else "Unknown",
            updated_at=s.updated_at
        ))
    return result

@router.get("/summary", response_model=List[StockSummary])
def stock_summary(db: Session = Depends(get_db), current_user = Depends(require_permission("stock:read"))):
    products = db.query(Product).filter(Product.is_active == True).all()
    result = []
    for p in products:
        total = db.query(func.coalesce(func.sum(Batch.quantity_available), 0)).filter(Batch.product_id == p.id).scalar()
        stocks = db.query(Stock).filter(Stock.product_id == p.id).all()
        locs = []
        for s in stocks:
            loc_name = db.query(WarehouseLocation).filter(WarehouseLocation.id == s.location_id).first()
            locs.append({"location_id": s.location_id, "location_name": loc_name.name if loc_name else "Unknown", "quantity": s.quantity})
        result.append(StockSummary(
            product_id=p.id,
            product_name=p.name,
            product_sku=p.sku,
            total_quantity=total or Decimal("0"),
            locations=locs
        ))
    return result

@router.get("/low")
def low_stock(db: Session = Depends(get_db), current_user = Depends(require_permission("stock:read"))):
    products = db.query(Product).filter(Product.is_active == True).all()
    low = []
    for p in products:
        total = db.query(func.coalesce(func.sum(Batch.quantity_available), 0)).filter(Batch.product_id == p.id).scalar() or 0
        if total <= p.min_stock:
            low.append({
                "product_id": p.id,
                "product_name": p.name,
                "sku": p.sku,
                "ean": p.ean,
                "current_stock": total,
                "min_stock": p.min_stock,
                "target_stock": p.target_stock,
                "safety_stock": p.safety_stock
            })
    return low
