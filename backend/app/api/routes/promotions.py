from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from datetime import datetime, date, timedelta
from decimal import Decimal
from app.core.database import get_db
from app.core.deps import get_current_user, require_permission
from app.models.promotion import Promotion, PromotionStatus
from app.models.batch import Batch
from app.models.product import Product
from pydantic import BaseModel, ConfigDict
from app.services.audit import add_audit_log
from app.services.smart_markdown import build_markdown_suggestions

router = APIRouter()

class PromotionCreate(BaseModel):
    product_id: int
    batch_id: Optional[int] = None
    discounted_price: Decimal
    reason: Optional[str] = None
    end_date: Optional[datetime] = None
    strategy: str = "MANUAL"
    recommendation_data: Optional[dict] = None

class PromotionOut(BaseModel):
    id: int
    product_id: int
    product_name: Optional[str] = None
    batch_id: Optional[int]
    original_price: Decimal
    discounted_price: Decimal
    discount_percent: Decimal
    reason: Optional[str]
    strategy: str
    recommendation_data: Optional[dict] = None
    status: str
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

@router.get("", response_model=List[PromotionOut])
def list_promotions(status: Optional[str] = None, db: Session = Depends(get_db), current_user = Depends(require_permission("promotions:read"))):
    q = db.query(Promotion).filter(Promotion.tenant_id == current_user.tenant_id).order_by(Promotion.created_at.desc())
    if status:
        q = q.filter(Promotion.status == status)
    promos = q.limit(200).all()
    result = []
    for p in promos:
        out = PromotionOut.model_validate(p)
        prod = db.query(Product).filter(Product.id == p.product_id).first()
        out.product_name = prod.name if prod else "Unknown"
        result.append(out)
    return result

@router.get("/suggestions")
def promotion_suggestions(db: Session = Depends(get_db), current_user = Depends(require_permission("promotions:read"))):
    return build_markdown_suggestions(db, current_user.tenant_id)

@router.post("", response_model=PromotionOut)
def create_promotion(payload: PromotionCreate, db: Session = Depends(get_db), current_user = Depends(require_permission("promotions:write"))):
    product = db.query(Product).filter(Product.id == payload.product_id, Product.tenant_id == current_user.tenant_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    if payload.discounted_price >= product.selling_price:
        raise HTTPException(status_code=400, detail="Cena promocyjna musi być niższa niż regularna")
    
    discount_percent = ((product.selling_price - payload.discounted_price) / product.selling_price * 100) if product.selling_price > 0 else Decimal(0)
    
    if payload.batch_id and not db.query(Batch.id).filter(Batch.id == payload.batch_id, Batch.product_id == product.id, Batch.tenant_id == current_user.tenant_id).first():
        raise HTTPException(status_code=422, detail="Partia nie istnieje w tym sklepie")
    promo = Promotion(
        tenant_id=current_user.tenant_id,
        product_id=payload.product_id,
        batch_id=payload.batch_id,
        original_price=product.selling_price,
        discounted_price=payload.discounted_price,
        discount_percent=discount_percent,
        reason=payload.reason,
        strategy=payload.strategy.upper()[:40],
        recommendation_data=payload.recommendation_data,
        status=PromotionStatus.SUGGESTED,
        created_by=current_user.id,
        end_date=payload.end_date
    )
    db.add(promo)
    db.flush()
    add_audit_log(db, user_id=current_user.id, action="CREATE", entity_type="promotion", entity_id=promo.id, new_values={"product_id": promo.product_id, "batch_id": promo.batch_id, "discount_percent": promo.discount_percent, "strategy": promo.strategy})
    db.commit()
    db.refresh(promo)
    
    out = PromotionOut.model_validate(promo)
    out.product_name = product.name
    return out

@router.put("/{promo_id}/approve")
def approve_promotion(promo_id: int, db: Session = Depends(get_db), current_user = Depends(require_permission("promotions:write"))):
    promo = db.query(Promotion).filter(Promotion.id == promo_id, Promotion.tenant_id == current_user.tenant_id).first()
    if not promo:
        raise HTTPException(status_code=404, detail="Not found")
    promo.status = PromotionStatus.ACTIVE
    promo.approved_by = current_user.id
    promo.start_date = datetime.utcnow()
    add_audit_log(db, user_id=current_user.id, action="APPROVE", entity_type="promotion", entity_id=promo.id, new_values={"status": PromotionStatus.ACTIVE.value})
    db.commit()
    return {"message": "Approved"}

@router.put("/{promo_id}/activate")
def activate_promotion(promo_id: int, db: Session = Depends(get_db), current_user = Depends(require_permission("promotions:write"))):
    promo = db.query(Promotion).filter(Promotion.id == promo_id, Promotion.tenant_id == current_user.tenant_id).first()
    if not promo:
        raise HTTPException(status_code=404, detail="Not found")
    promo.status = PromotionStatus.ACTIVE
    promo.start_date = datetime.utcnow()
    db.commit()
    return {"message": "Activated"}
