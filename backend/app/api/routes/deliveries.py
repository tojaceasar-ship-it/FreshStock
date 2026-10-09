from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import date, datetime
from decimal import Decimal
from app.core.database import get_db
from app.core.deps import get_current_user, require_permission
from app.models.delivery import Delivery, DeliveryItem, DeliveryStatus
from app.models.batch import Batch
from app.models.stock import Stock
from app.models.stock_movement import StockMovement, MovementType
from app.models.product import Product
from app.models.purchase_order import PurchaseOrder, PurchaseOrderItem, POStatus
from app.services.audit import add_audit_log
from pydantic import BaseModel, ConfigDict, Field
from app.core.quantities import QuantityValidationError, quantity_for_unit

router = APIRouter()

class DeliveryItemCreate(BaseModel):
    product_id: int
    quantity_ordered: Decimal = Field(default=Decimal("0"), ge=0, max_digits=14, decimal_places=3)
    quantity_received: Decimal = Field(gt=0, max_digits=14, decimal_places=3)
    purchase_price: Decimal
    expiry_date: Optional[date] = None
    batch_number: Optional[str] = None
    location_id: Optional[int] = None
    notes: Optional[str] = None

class DeliveryCreate(BaseModel):
    supplier_id: Optional[int] = None
    purchase_order_id: Optional[int] = None
    document_number: str
    notes: Optional[str] = None
    items: List[DeliveryItemCreate]

class DeliveryItemOut(BaseModel):
    id: int
    delivery_id: int
    product_id: int
    product_name: Optional[str] = None
    quantity_ordered: Decimal
    quantity_received: Decimal
    purchase_price: Decimal
    expiry_date: Optional[date]
    batch_number: Optional[str]
    location_id: Optional[int]
    model_config = ConfigDict(from_attributes=True)

class DeliveryOut(BaseModel):
    id: int
    supplier_id: Optional[int]
    purchase_order_id: Optional[int]
    supplier_name: Optional[str] = None
    document_number: str
    status: str
    total_value: Decimal
    notes: Optional[str]
    delivered_at: Optional[datetime]
    created_at: datetime
    items: List[DeliveryItemOut] = []
    model_config = ConfigDict(from_attributes=True)

@router.get("", response_model=List[DeliveryOut])
def list_deliveries(db: Session = Depends(get_db), current_user = Depends(require_permission("deliveries:read"))):
    deliveries = db.query(Delivery).filter(Delivery.tenant_id == current_user.tenant_id).order_by(Delivery.created_at.desc()).all()
    result = []
    for d in deliveries:
        out = DeliveryOut.model_validate(d)
        out.supplier_name = d.supplier.name if d.supplier else None
        out.items = []
        for item in d.items:
            item_out = DeliveryItemOut.model_validate(item)
            prod = db.query(Product).filter(Product.id == item.product_id, Product.tenant_id == current_user.tenant_id).first()
            item_out.product_name = prod.name if prod else "Unknown"
            out.items.append(item_out)
        result.append(out)
    return result

@router.get("/{delivery_id}", response_model=DeliveryOut)
def get_delivery(delivery_id: int, db: Session = Depends(get_db), current_user = Depends(require_permission("deliveries:read"))):
    d = db.query(Delivery).filter(Delivery.id == delivery_id, Delivery.tenant_id == current_user.tenant_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Not found")
    out = DeliveryOut.model_validate(d)
    out.supplier_name = d.supplier.name if d.supplier else None
    out.items = []
    for item in d.items:
        item_out = DeliveryItemOut.model_validate(item)
        prod = db.query(Product).filter(Product.id == item.product_id, Product.tenant_id == current_user.tenant_id).first()
        item_out.product_name = prod.name if prod else "Unknown"
        out.items.append(item_out)
    return out

@router.post("", response_model=DeliveryOut)
def create_delivery(payload: DeliveryCreate, db: Session = Depends(get_db), current_user = Depends(require_permission("deliveries:create"))):
    # Transaction: create delivery, batches, stock, movements
    try:
        total_value = sum(item.quantity_received * item.purchase_price for item in payload.items)
        
        po = None
        if payload.purchase_order_id is not None:
            po = db.query(PurchaseOrder).filter(
                PurchaseOrder.id == payload.purchase_order_id,
                PurchaseOrder.tenant_id == current_user.tenant_id,
            ).with_for_update().first()
            if not po:
                raise HTTPException(status_code=404, detail="Purchase order not found")
            if po.status not in {POStatus.CONFIRMED, POStatus.PARTIALLY_DELIVERED}:
                raise HTTPException(status_code=409, detail="Purchase order is not ready for receipt")
            if payload.supplier_id is not None and po.supplier_id != payload.supplier_id:
                raise HTTPException(status_code=400, detail="Supplier does not match purchase order")

        delivery = Delivery(
            tenant_id=current_user.tenant_id,
            supplier_id=payload.supplier_id,
            purchase_order_id=payload.purchase_order_id,
            document_number=payload.document_number,
            status=DeliveryStatus.RECEIVED,
            total_value=total_value,
            notes=payload.notes,
            delivered_at=datetime.utcnow(),
            created_by=current_user.id
        )
        db.add(delivery)
        db.flush()  # get delivery id
        
        for item_data in payload.items:
            product = db.query(Product).filter(Product.id == item_data.product_id, Product.tenant_id == current_user.tenant_id).first()
            if not product:
                raise HTTPException(status_code=400, detail=f"Produkt {item_data.product_id} nie istnieje")
            try:
                item_data.quantity_received = quantity_for_unit(item_data.quantity_received, product.unit)
                item_data.quantity_ordered = quantity_for_unit(item_data.quantity_ordered, product.unit, allow_zero=True)
            except QuantityValidationError as exc:
                raise HTTPException(status_code=422, detail=str(exc))
            
            batch_number = item_data.batch_number or f"{payload.document_number}-{item_data.product_id}-{datetime.utcnow().strftime('%Y%m%d')}"
            
            batch = Batch(
                tenant_id=current_user.tenant_id,
                product_id=item_data.product_id,
                batch_number=batch_number,
                expiry_date=item_data.expiry_date,
                quantity_received=item_data.quantity_received,
                quantity_available=item_data.quantity_received,
                purchase_price=item_data.purchase_price,
                supplier_id=payload.supplier_id,
                delivery_id=delivery.id,
                warehouse_location_id=item_data.location_id
            )
            db.add(batch)
            db.flush()
            
            # Update stock table
            if item_data.location_id:
                stock = db.query(Stock).filter(Stock.tenant_id == current_user.tenant_id, Stock.product_id == item_data.product_id, Stock.location_id == item_data.location_id).first()
                if stock:
                    stock.quantity += item_data.quantity_received
                else:
                    stock = Stock(tenant_id=current_user.tenant_id, product_id=item_data.product_id, location_id=item_data.location_id, quantity=item_data.quantity_received)
                    db.add(stock)
            
            # Create delivery item
            d_item = DeliveryItem(
                tenant_id=current_user.tenant_id,
                delivery_id=delivery.id,
                product_id=item_data.product_id,
                batch_id=batch.id,
                quantity_ordered=item_data.quantity_ordered,
                quantity_received=item_data.quantity_received,
                purchase_price=item_data.purchase_price,
                expiry_date=item_data.expiry_date,
                batch_number=batch_number,
                location_id=item_data.location_id,
                notes=item_data.notes
            )
            db.add(d_item)
            
            # Create stock movement
            movement = StockMovement(
                tenant_id=current_user.tenant_id,
                product_id=item_data.product_id,
                batch_id=batch.id,
                quantity=item_data.quantity_received,
                movement_type=MovementType.DELIVERY,
                destination_location_id=item_data.location_id,
                user_id=current_user.id,
                reason=f"Dostawa {payload.document_number}",
                reference_id=str(delivery.id),
                reference_type="delivery"
            )
            db.add(movement)

            if po:
                po_item = db.query(PurchaseOrderItem).filter(
                    PurchaseOrderItem.purchase_order_id == po.id,
                    PurchaseOrderItem.product_id == item_data.product_id,
                    PurchaseOrderItem.tenant_id == current_user.tenant_id,
                ).first()
                if not po_item:
                    raise HTTPException(status_code=400, detail=f"Product {item_data.product_id} is not on purchase order")
                if po_item.quantity_received + item_data.quantity_received > po_item.quantity:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Receipt exceeds ordered quantity for product {item_data.product_id}",
                    )
                po_item.quantity_received += item_data.quantity_received

        if po:
            received_all = all(item.quantity_received >= item.quantity for item in po.items)
            received_any = any(item.quantity_received > 0 for item in po.items)
            po.status = POStatus.DELIVERED if received_all else POStatus.PARTIALLY_DELIVERED if received_any else POStatus.CONFIRMED
        
        # Audit log
        add_audit_log(
            db, user_id=current_user.id, action="CREATE", entity_type="delivery", entity_id=delivery.id,
            new_values={"document_number": payload.document_number, "total_value": total_value, "items": [item.model_dump() for item in payload.items]},
            details=f"Przyjęto dostawę {payload.document_number} i zwiększono stan magazynowy",
        )
        
        db.commit()
        db.refresh(delivery)
        
        out = DeliveryOut.model_validate(delivery)
        out.supplier_name = delivery.supplier.name if delivery.supplier else None
        out.items = []
        for item in delivery.items:
            item_out = DeliveryItemOut.model_validate(item)
            prod = db.query(Product).filter(Product.id == item.product_id, Product.tenant_id == current_user.tenant_id).first()
            item_out.product_name = prod.name if prod else "Unknown"
            out.items.append(item_out)
        return out
        
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Błąd przyjęcia dostawy: {str(e)}")
