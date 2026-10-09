from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
from decimal import Decimal
from app.core.database import get_db
from app.core.deps import get_current_user, require_permission
from app.models.waste import Waste, WasteReason
from app.models.batch import Batch
from app.models.stock import Stock
from app.models.stock_movement import StockMovement, MovementType
from app.models.product import Product
from pydantic import BaseModel, ConfigDict, Field
from app.core.quantities import QuantityValidationError, quantity_for_unit
from app.services.audit import add_audit_log

router = APIRouter()

class WasteCreate(BaseModel):
    product_id: int
    batch_id: Optional[int] = None
    quantity: Decimal = Field(gt=0, max_digits=14, decimal_places=3)
    reason: str
    notes: Optional[str] = None
    location_id: Optional[int] = None

class WasteOut(BaseModel):
    id: int
    product_id: int
    product_name: Optional[str] = None
    batch_id: Optional[int]
    quantity: Decimal
    purchase_value: Decimal
    sale_value: Decimal
    reason: str
    notes: Optional[str]
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

@router.get("", response_model=List[WasteOut])
def list_waste(reason: Optional[str] = None, db: Session = Depends(get_db), current_user = Depends(require_permission("waste:read"))):
    q = db.query(Waste).order_by(Waste.created_at.desc())
    if reason:
        q = q.filter(Waste.reason == reason)
    wastes = q.limit(200).all()
    result = []
    for w in wastes:
        out = WasteOut.model_validate(w)
        prod = db.query(Product).filter(Product.id == w.product_id).first()
        out.product_name = prod.name if prod else "Unknown"
        result.append(out)
    return result

@router.post("", response_model=WasteOut)
def create_waste(payload: WasteCreate, db: Session = Depends(get_db), current_user = Depends(require_permission("waste:create"))):
    product = db.query(Product).filter(Product.id == payload.product_id, Product.tenant_id == current_user.tenant_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    try:
        payload.quantity = quantity_for_unit(payload.quantity, product.unit)
    except QuantityValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    
    try:
        reason_enum = WasteReason(payload.reason)
    except:
        raise HTTPException(status_code=400, detail="Invalid reason")
    
    # FEFO-like removal if batch not specified
    remaining = payload.quantity
    batches_to_update = []
    
    if payload.batch_id:
        batch = db.query(Batch).filter(Batch.id == payload.batch_id).first()
        if not batch or batch.product_id != payload.product_id:
            raise HTTPException(status_code=400, detail="Invalid batch")
        if batch.quantity_available < payload.quantity:
            raise HTTPException(status_code=400, detail="Niewystarczający stan w partii")
        batches_to_update.append((batch, payload.quantity))
    else:
        # Take from oldest batches first
        batches = db.query(Batch).filter(Batch.product_id == payload.product_id, Batch.quantity_available > 0).order_by(Batch.expiry_date.asc().nulls_last()).all()
        for b in batches:
            if remaining <= 0:
                break
            take = min(remaining, b.quantity_available)
            batches_to_update.append((b, take))
            remaining -= take
        if remaining > 0:
            raise HTTPException(status_code=400, detail="Niewystarczający stan magazynowy")
    
    purchase_value = Decimal(0)
    sale_value = Decimal(0)
    waste_movements = []
    
    for batch, qty in batches_to_update:
        batch.quantity_available -= qty
        purchase_value += (batch.purchase_price or product.purchase_price) * qty
        sale_value += product.selling_price * qty
        
        if batch.warehouse_location_id:
            stock = db.query(Stock).filter(Stock.product_id == payload.product_id, Stock.location_id == batch.warehouse_location_id).first()
            if stock:
                stock.quantity -= qty
        
        movement = StockMovement(
            product_id=payload.product_id,
            batch_id=batch.id,
            quantity=-qty,
            movement_type=MovementType.WASTE if reason_enum != WasteReason.EXPIRED else MovementType.EXPIRED,
            source_location_id=batch.warehouse_location_id,
            user_id=current_user.id,
            reason=f"Strata: {reason_enum.value} - {payload.notes or ''}",
            reference_type="waste"
        )
        db.add(movement)
        waste_movements.append(movement)
    
    waste = Waste(
        product_id=payload.product_id,
        batch_id=payload.batch_id,
        quantity=payload.quantity,
        purchase_value=purchase_value,
        sale_value=sale_value,
        reason=reason_enum,
        notes=payload.notes,
        reported_by=current_user.id,
        location_id=payload.location_id
    )
    db.add(waste)
    db.flush()
    for movement in waste_movements:
        movement.reference_id = str(waste.id)
    add_audit_log(
        db, user_id=current_user.id, action="CREATE", entity_type="waste", entity_id=waste.id,
        new_values={"product_id": payload.product_id, "batch_id": payload.batch_id, "quantity": payload.quantity, "reason": reason_enum, "purchase_value": purchase_value, "affected_batches": [{"batch_id": batch.id, "quantity_removed": qty} for batch, qty in batches_to_update]},
        details="Zarejestrowano stratę i zmniejszono stan magazynowy",
    )
    db.commit()
    db.refresh(waste)
    
    out = WasteOut.model_validate(waste)
    out.product_name = product.name
    return out

@router.get("/stats")
def waste_stats(db: Session = Depends(get_db), current_user = Depends(require_permission("waste:read"))):
    from sqlalchemy import func
    from datetime import timedelta
    
    total = db.query(func.coalesce(func.sum(Waste.purchase_value), 0)).scalar() or 0
    today = datetime.utcnow().date()
    week_ago = datetime.utcnow() - timedelta(days=7)
    month_ago = datetime.utcnow() - timedelta(days=30)
    
    today_val = db.query(func.coalesce(func.sum(Waste.purchase_value), 0)).filter(Waste.created_at >= today).scalar() or 0
    week_val = db.query(func.coalesce(func.sum(Waste.purchase_value), 0)).filter(Waste.created_at >= week_ago).scalar() or 0
    month_val = db.query(func.coalesce(func.sum(Waste.purchase_value), 0)).filter(Waste.created_at >= month_ago).scalar() or 0
    
    by_reason = db.query(Waste.reason, func.sum(Waste.purchase_value), func.count(Waste.id)).group_by(Waste.reason).all()
    
    return {
        "total_value": float(total),
        "today": float(today_val),
        "week": float(week_val),
        "month": float(month_val),
        "by_reason": [{"reason": r[0].value if hasattr(r[0], 'value') else str(r[0]), "value": float(r[1]), "count": r[2]} for r in by_reason]
    }
