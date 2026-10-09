from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from datetime import date, datetime
from decimal import Decimal
from app.core.database import get_db
from app.core.deps import get_current_user, require_permission
from app.models.purchase_order import PurchaseOrder, PurchaseOrderItem, POStatus
from app.models.product import Product
from app.models.batch import Batch
from app.models.supplier import Supplier
from app.models.sale import Sale, SaleItem
from pydantic import BaseModel, ConfigDict, Field
from app.core.quantities import QuantityValidationError, quantity_for_unit

router = APIRouter()

class POItemCreate(BaseModel):
    product_id: int
    quantity: Decimal = Field(gt=0, max_digits=14, decimal_places=3)
    purchase_price: Decimal

class POCreate(BaseModel):
    supplier_id: int
    expected_delivery_date: Optional[date] = None
    notes: Optional[str] = None
    items: List[POItemCreate]

class POItemOut(BaseModel):
    id: int
    purchase_order_id: int
    product_id: int
    product_name: Optional[str] = None
    quantity: Decimal
    purchase_price: Decimal
    quantity_received: Decimal
    model_config = ConfigDict(from_attributes=True)

class POOut(BaseModel):
    id: int
    supplier_id: Optional[int]
    supplier_name: Optional[str] = None
    order_number: str
    status: str
    total_value: Decimal
    expected_delivery_date: Optional[date]
    notes: Optional[str]
    created_at: datetime
    items: List[POItemOut] = []
    model_config = ConfigDict(from_attributes=True)

def generate_order_number():
    import uuid
    return f"PO-{datetime.utcnow().strftime('%Y%m%d')}-{uuid.uuid4().hex[:10].upper()}"

@router.get("", response_model=List[POOut])
def list_pos(db: Session = Depends(get_db), current_user = Depends(require_permission("orders:read"))):
    pos = db.query(PurchaseOrder).filter(PurchaseOrder.tenant_id == current_user.tenant_id).order_by(PurchaseOrder.created_at.desc()).all()
    result = []
    for po in pos:
        out = POOut.model_validate(po)
        out.supplier_name = po.supplier.name if po.supplier else None
        out.items = []
        for item in po.items:
            item_out = POItemOut.model_validate(item)
            prod = db.query(Product).filter(Product.id == item.product_id, Product.tenant_id == current_user.tenant_id).first()
            item_out.product_name = prod.name if prod else "Unknown"
            out.items.append(item_out)
        result.append(out)
    return result

@router.post("", response_model=POOut)
def create_po(payload: POCreate, db: Session = Depends(get_db), current_user = Depends(require_permission("orders:write"))):
    supplier = db.query(Supplier).filter(Supplier.id == payload.supplier_id, Supplier.tenant_id == current_user.tenant_id).first()
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")
    if not payload.items or any(item.quantity <= 0 or item.purchase_price < 0 for item in payload.items):
        raise HTTPException(status_code=400, detail="Invalid purchase order items")
    product_ids = {item.product_id for item in payload.items}
    products = db.query(Product).filter(Product.tenant_id == current_user.tenant_id, Product.id.in_(product_ids)).all()
    products_by_id = {product.id: product for product in products}
    if set(products_by_id) != product_ids:
        raise HTTPException(status_code=404, detail="Product not found")
    try:
        for item in payload.items:
            item.quantity = quantity_for_unit(item.quantity, products_by_id[item.product_id].unit)
    except QuantityValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    total = sum(i.quantity * i.purchase_price for i in payload.items)
    po = PurchaseOrder(
        tenant_id=current_user.tenant_id,
        supplier_id=payload.supplier_id,
        order_number=generate_order_number(),
        status=POStatus.DRAFT,
        total_value=total,
        expected_delivery_date=payload.expected_delivery_date,
        notes=payload.notes,
        created_by=current_user.id
    )
    db.add(po)
    db.flush()
    for item in payload.items:
        po_item = PurchaseOrderItem(
            tenant_id=current_user.tenant_id,
            purchase_order_id=po.id,
            product_id=item.product_id,
            quantity=item.quantity,
            purchase_price=item.purchase_price
        )
        db.add(po_item)
    db.commit()
    db.refresh(po)
    out = POOut.model_validate(po)
    out.supplier_name = po.supplier.name if po.supplier else None
    out.items = [POItemOut.model_validate(i) for i in po.items]
    return out

@router.get("/suggestions")
def get_suggestions(db: Session = Depends(get_db), current_user = Depends(require_permission("orders:read"))):
    # Reorder point logic: average_daily_sales * lead_time + safety_stock
    products = db.query(Product).filter(Product.tenant_id == current_user.tenant_id, Product.is_active == True).all()
    suggestions = []
    
    for product in products:
        total_stock = db.query(func.coalesce(func.sum(Batch.quantity_available), 0)).filter(Batch.tenant_id == current_user.tenant_id, Batch.product_id == product.id).scalar() or 0
        
        # Calculate average daily sales from last 30 days
        from datetime import timedelta, timezone
        thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
        sales_qty = db.query(func.coalesce(func.sum(SaleItem.quantity), 0)).join(Sale).filter(
            SaleItem.product_id == product.id,
            SaleItem.tenant_id == current_user.tenant_id,
            Sale.tenant_id == current_user.tenant_id,
            Sale.sale_date >= thirty_days_ago
        ).scalar() or 0
        
        avg_daily = float(sales_qty) / 30 if sales_qty else 0.5  # default small value if no sales
        
        # Get lead time from supplier
        supplier = db.query(Supplier).filter(Supplier.id == product.default_supplier_id, Supplier.tenant_id == current_user.tenant_id).first() if product.default_supplier_id else None
        lead_time = supplier.lead_time_days if supplier else 2
        
        # Cast Decimal fields to float for arithmetic
        safety_stock = float(product.safety_stock)
        reorder_point = avg_daily * lead_time + safety_stock
        target = float(product.target_stock)
        
        if float(total_stock) <= reorder_point:
            suggested_qty = max(0, target - float(total_stock))
            if suggested_qty > 0:
                suggestions.append({
                    "product_id": product.id,
                    "product_name": product.name,
                    "sku": product.sku,
                    "ean": product.ean,
                    "current_stock": float(total_stock),
                    "min_stock": float(product.min_stock),
                    "target_stock": target,
                    "safety_stock": safety_stock,
                    "avg_daily_sales": round(avg_daily, 2),
                    "lead_time_days": lead_time,
                    "reorder_point": round(reorder_point, 2),
                    "suggested_quantity": suggested_qty,
                    "supplier_id": product.default_supplier_id,
                    "supplier_name": supplier.name if supplier else None,
                    "purchase_price": float(product.purchase_price)
                })
    
    return sorted(suggestions, key=lambda x: x["current_stock"])

@router.put("/{po_id}/status")
def update_status(po_id: int, status: str, db: Session = Depends(get_db), current_user = Depends(require_permission("orders:write"))):
    po = db.query(PurchaseOrder).filter(PurchaseOrder.id == po_id, PurchaseOrder.tenant_id == current_user.tenant_id).first()
    if not po:
        raise HTTPException(status_code=404, detail="Not found")
    try:
        requested = POStatus(status)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid status")
    allowed = {
        POStatus.DRAFT: {POStatus.SENT, POStatus.CANCELLED},
        POStatus.SENT: {POStatus.CONFIRMED, POStatus.CANCELLED},
        POStatus.CONFIRMED: {POStatus.CANCELLED},
        POStatus.PARTIALLY_DELIVERED: {POStatus.CANCELLED},
        POStatus.DELIVERED: set(),
        POStatus.CANCELLED: set(),
    }
    if requested != po.status and requested not in allowed[po.status]:
        raise HTTPException(status_code=409, detail=f"Invalid status transition: {po.status.value} -> {requested.value}")
    po.status = requested
    db.commit()
    return {"message": "Status updated", "status": po.status}

@router.get("/{po_id}", response_model=POOut)
def get_po(po_id: int, db: Session = Depends(get_db), current_user = Depends(require_permission("orders:read"))):
    po = db.query(PurchaseOrder).filter(PurchaseOrder.id == po_id, PurchaseOrder.tenant_id == current_user.tenant_id).first()
    if not po:
        raise HTTPException(status_code=404, detail="Not found")
    out = POOut.model_validate(po)
    out.supplier_name = po.supplier.name if po.supplier else None
    out.items = []
    for item in po.items:
        item_out = POItemOut.model_validate(item)
        prod = db.query(Product).filter(Product.id == item.product_id, Product.tenant_id == current_user.tenant_id).first()
        item_out.product_name = prod.name if prod else "Unknown"
        out.items.append(item_out)
    return out
