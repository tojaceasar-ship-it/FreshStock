from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, date, timedelta
from app.core.database import get_db
from app.core.deps import get_current_user, require_permission
from app.models.alert import Alert, AlertSeverity, AlertType
from app.models.batch import Batch
from app.models.product import Product
from app.models.onboarding import StoreSettings
from sqlalchemy import func
from pydantic import BaseModel, ConfigDict

router = APIRouter()

class AlertOut(BaseModel):
    id: int
    alert_type: str
    severity: str
    title: str
    message: str
    product_id: Optional[int]
    product_name: Optional[str] = None
    batch_id: Optional[int]
    is_read: bool
    is_resolved: bool
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

@router.get("", response_model=List[AlertOut])
def list_alerts(
    severity: Optional[str] = None,
    is_resolved: Optional[bool] = None,
    is_read: Optional[bool] = None,
    db: Session = Depends(get_db),
    current_user = Depends(require_permission("alerts:read"))
):
    q = db.query(Alert).filter(Alert.tenant_id == current_user.tenant_id).order_by(Alert.created_at.desc(), Alert.id.desc())
    if severity:
        q = q.filter(Alert.severity == severity)
    if is_resolved is not None:
        q = q.filter(Alert.is_resolved == is_resolved)
    if is_read is not None:
        q = q.filter(Alert.is_read == is_read)
    
    alerts = q.limit(200).all()
    result = []
    for a in alerts:
        out = AlertOut.model_validate(a)
        if a.product_id:
            prod = db.query(Product).filter(Product.id == a.product_id, Product.tenant_id == current_user.tenant_id).first()
            out.product_name = prod.name if prod else None
        result.append(out)
    return result

@router.post("/generate")
def generate_alerts(db: Session = Depends(get_db), current_user = Depends(require_permission("alerts:write"))):
    """Generate alerts based on current stock and expiry"""
    today = date.today()
    generated = 0
    
    # Get store settings for expiry rules
    store = db.query(StoreSettings).filter_by(tenant_id=current_user.tenant_id).first()
    expiry_rules = sorted(set(int(x) for x in (store.expiry_rules if store else [7, 3, 1]) if int(x) >= 0), reverse=True) if store else [7, 3, 1]
    
    # Clear old unresolved auto-generated? Keep for history, just generate new
    
    # Expired products
    expired_batches = db.query(Batch).filter(Batch.tenant_id == current_user.tenant_id, Batch.expiry_date < today, Batch.quantity_available > 0).all()
    for batch in expired_batches:
        existing = db.query(Alert).filter(Alert.tenant_id == current_user.tenant_id, Alert.batch_id == batch.id, Alert.alert_type == AlertType.EXPIRED, Alert.is_resolved == False).first()
        if existing:
            continue
        product = db.query(Product).filter(Product.id == batch.product_id, Product.tenant_id == current_user.tenant_id).first()
        alert = Alert(
            tenant_id=current_user.tenant_id,
            alert_type=AlertType.EXPIRED,
            severity=AlertSeverity.CRITICAL,
            title=f"Produkt przeterminowany: {product.name if product else batch.product_id}",
            message=f"Partia {batch.batch_number} wygasła {batch.expiry_date}, ilość: {batch.quantity_available}",
            product_id=batch.product_id,
            batch_id=batch.id,
            location_id=batch.warehouse_location_id
        )
        db.add(alert)
        generated += 1
    
    # Expiring soon - use configured expiry rules
    for days in expiry_rules:
        severity = AlertSeverity.HIGH if days <= 1 else (AlertSeverity.MEDIUM if days <= 3 else AlertSeverity.LOW)
        threshold = today + timedelta(days=days)
        batches = db.query(Batch).filter(Batch.tenant_id == current_user.tenant_id, Batch.expiry_date == threshold, Batch.quantity_available > 0).all()
        for batch in batches:
            existing = db.query(Alert).filter(Alert.tenant_id == current_user.tenant_id, Alert.batch_id == batch.id, Alert.alert_type == AlertType.EXPIRING_SOON, Alert.is_resolved == False).first()
            if existing:
                continue
            product = db.query(Product).filter(Product.id == batch.product_id, Product.tenant_id == current_user.tenant_id).first()
            alert = Alert(
                tenant_id=current_user.tenant_id,
                alert_type=AlertType.EXPIRING_SOON,
                severity=severity,
                title=f"Kończy się termin ({days} dni): {product.name if product else batch.product_id}",
                message=f"Partia {batch.batch_number} wygasa {batch.expiry_date}, ilość: {batch.quantity_available}",
                product_id=batch.product_id,
                batch_id=batch.id,
                location_id=batch.warehouse_location_id
            )
            db.add(alert)
            generated += 1
    
    # Low stock and out of stock
    products = db.query(Product).filter(Product.tenant_id == current_user.tenant_id, Product.is_active == True).all()
    for product in products:
        total = db.query(func.coalesce(func.sum(Batch.quantity_available), 0)).filter(Batch.tenant_id == current_user.tenant_id, Batch.product_id == product.id).scalar() or 0
        if total == 0:
            existing = db.query(Alert).filter(Alert.tenant_id == current_user.tenant_id, Alert.product_id == product.id, Alert.alert_type == AlertType.OUT_OF_STOCK, Alert.is_resolved == False).first()
            if not existing:
                alert = Alert(
                    tenant_id=current_user.tenant_id,
                    alert_type=AlertType.OUT_OF_STOCK,
                    severity=AlertSeverity.CRITICAL,
                    title=f"Brak towaru: {product.name}",
                    message=f"Produkt {product.sku} - stan 0, min: {product.min_stock}",
                    product_id=product.id
                )
                db.add(alert)
                generated += 1
        elif total <= product.min_stock:
            existing = db.query(Alert).filter(Alert.tenant_id == current_user.tenant_id, Alert.product_id == product.id, Alert.alert_type == AlertType.LOW_STOCK, Alert.is_resolved == False).first()
            if not existing:
                sev = AlertSeverity.CRITICAL if total <= product.safety_stock else AlertSeverity.HIGH
                alert = Alert(
                    tenant_id=current_user.tenant_id,
                    alert_type=AlertType.LOW_STOCK,
                    severity=sev,
                    title=f"Niski stan: {product.name}",
                    message=f"Stan {total}, minimum {product.min_stock}, docelowy {product.target_stock}",
                    product_id=product.id
                )
                db.add(alert)
                generated += 1
    
    db.commit()
    return {"generated": generated}

@router.put("/{alert_id}/read")
def mark_read(alert_id: int, db: Session = Depends(get_db), current_user = Depends(require_permission("alerts:read"))):
    alert = db.query(Alert).filter(Alert.id == alert_id, Alert.tenant_id == current_user.tenant_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Not found")
    alert.is_read = True
    db.commit()
    return {"message": "Marked as read"}

@router.put("/{alert_id}/resolve")
def resolve_alert(alert_id: int, db: Session = Depends(get_db), current_user = Depends(require_permission("alerts:write"))):
    alert = db.query(Alert).filter(Alert.id == alert_id, Alert.tenant_id == current_user.tenant_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Not found")
    alert.is_resolved = True
    alert.resolved_at = datetime.utcnow()
    db.commit()
    return {"message": "Resolved"}

@router.put("/read-all")
def read_all(db: Session = Depends(get_db), current_user = Depends(require_permission("alerts:read"))):
    db.query(Alert).filter(Alert.tenant_id == current_user.tenant_id, Alert.is_read == False).update({"is_read": True})
    db.commit()
    return {"message": "All marked as read"}
