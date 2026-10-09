from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
from decimal import Decimal
from app.core.database import get_db
from app.core.deps import get_current_user, require_permission
from app.models.inventory_count import InventoryCount, InventoryCountItem, CountStatus
from app.models.batch import Batch
from app.models.stock import Stock
from app.models.stock_movement import StockMovement, MovementType
from app.models.product import Product
from sqlalchemy import func
from pydantic import BaseModel, ConfigDict, Field
from app.core.quantities import QuantityValidationError, quantity_for_unit
from app.services.audit import add_audit_log

router = APIRouter()


def _apply_stock_delta(db: Session, product_id: int, location_id: Optional[int], delta: Decimal) -> None:
    """Move the aggregated stock row by `delta`, creating it if absent.

    Batch quantities and the aggregated `stock` row must stay in step; adjusting
    only one of them makes /stock and /stock/summary disagree with the batch
    ledger. `location_id` may be None, in which case no row is maintained.
    """
    if not location_id or delta == 0:
        return
    stock = db.query(Stock).filter(
        Stock.product_id == product_id,
        Stock.location_id == location_id,
    ).first()
    if stock:
        stock.quantity = max(0, stock.quantity + delta)
    else:
        db.add(Stock(product_id=product_id, location_id=location_id, quantity=max(0, delta)))


def _product_purchase_price(db: Session, product_id: int):
    product = db.query(Product).filter(Product.id == product_id).first()
    return product.purchase_price if product else None

class CountItemCreate(BaseModel):
    product_id: int
    batch_id: Optional[int] = None
    counted_quantity: Decimal = Field(ge=0, max_digits=14, decimal_places=3)
    reason: Optional[str] = None

class CountCreate(BaseModel):
    location_id: Optional[int] = None
    items: Optional[List[CountItemCreate]] = None

class CountItemOut(BaseModel):
    id: int
    count_id: int
    product_id: int
    product_name: Optional[str] = None
    batch_id: Optional[int]
    system_quantity: Decimal
    counted_quantity: Decimal
    difference: Decimal
    model_config = ConfigDict(from_attributes=True)

class CountOut(BaseModel):
    id: int
    count_number: str
    location_id: Optional[int]
    status: str
    created_at: datetime
    completed_at: Optional[datetime]
    items: List[CountItemOut] = []
    model_config = ConfigDict(from_attributes=True)

def gen_number():
    import random, string
    return f"INV-{datetime.utcnow().strftime('%Y%m%d')}-{''.join(random.choices(string.digits, k=4))}"

@router.get("", response_model=List[CountOut])
def list_counts(db: Session = Depends(get_db), current_user = Depends(require_permission("counts:read"))):
    counts = db.query(InventoryCount).order_by(InventoryCount.created_at.desc()).all()
    result = []
    for c in counts:
        out = CountOut.model_validate(c)
        out.items = []
        for item in c.items:
            item_out = CountItemOut.model_validate(item)
            prod = db.query(Product).filter(Product.id == item.product_id).first()
            item_out.product_name = prod.name if prod else "Unknown"
            out.items.append(item_out)
        result.append(out)
    return result

@router.post("", response_model=CountOut)
def create_count(payload: CountCreate, db: Session = Depends(get_db), current_user = Depends(require_permission("counts:write"))):
    count = InventoryCount(
        count_number=gen_number(),
        location_id=payload.location_id,
        status=CountStatus.DRAFT,
        created_by=current_user.id
    )
    db.add(count)
    db.flush()
    
    if payload.items:
        for item_data in payload.items:
            product = db.query(Product).filter(Product.id == item_data.product_id).first()
            if not product:
                raise HTTPException(status_code=404, detail="Product not found")
            try:
                item_data.counted_quantity = quantity_for_unit(item_data.counted_quantity, product.unit, allow_zero=True)
            except QuantityValidationError as exc:
                raise HTTPException(status_code=422, detail=str(exc))
            # Get system quantity
            if payload.location_id:
                system_qty = db.query(func.coalesce(func.sum(Batch.quantity_available), 0)).filter(
                    Batch.product_id == item_data.product_id,
                    Batch.warehouse_location_id == payload.location_id
                ).scalar() or 0
            else:
                system_qty = db.query(func.coalesce(func.sum(Batch.quantity_available), 0)).filter(
                    Batch.product_id == item_data.product_id
                ).scalar() or 0
            
            count_item = InventoryCountItem(
                count_id=count.id,
                product_id=item_data.product_id,
                batch_id=item_data.batch_id,
                system_quantity=system_qty,
                counted_quantity=item_data.counted_quantity,
                difference=item_data.counted_quantity - system_qty,
                reason=item_data.reason,
                counted_by=current_user.id
            )
            db.add(count_item)
    
    db.commit()
    db.refresh(count)
    out = CountOut.model_validate(count)
    out.items = [CountItemOut.model_validate(i) for i in count.items]
    return out

@router.post("/{count_id}/items", response_model=CountItemOut)
def add_item(count_id: int, payload: CountItemCreate, db: Session = Depends(get_db), current_user = Depends(require_permission("counts:write"))):
    count = db.query(InventoryCount).filter(InventoryCount.id == count_id).first()
    if not count:
        raise HTTPException(status_code=404, detail="Not found")
    if count.status == CountStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="Inwentaryzacja zakończona")
    product = db.query(Product).filter(Product.id == payload.product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    try:
        payload.counted_quantity = quantity_for_unit(payload.counted_quantity, product.unit, allow_zero=True)
    except QuantityValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    
    if count.location_id:
        system_qty = db.query(func.coalesce(func.sum(Batch.quantity_available), 0)).filter(
            Batch.product_id == payload.product_id,
            Batch.warehouse_location_id == count.location_id
        ).scalar() or 0
    else:
        system_qty = db.query(func.coalesce(func.sum(Batch.quantity_available), 0)).filter(
            Batch.product_id == payload.product_id
        ).scalar() or 0
    
    item = db.query(InventoryCountItem).filter(
        InventoryCountItem.count_id == count_id,
        InventoryCountItem.product_id == payload.product_id,
        InventoryCountItem.batch_id == payload.batch_id,
    ).first()
    old_values = None
    if item:
        old_values = {"counted_quantity": item.counted_quantity, "difference": item.difference, "reason": item.reason}
        item.counted_quantity = payload.counted_quantity
        item.difference = payload.counted_quantity - item.system_quantity
        item.reason = payload.reason
        item.counted_by = current_user.id
    else:
        item = InventoryCountItem(
            count_id=count_id,
            product_id=payload.product_id,
            batch_id=payload.batch_id,
            system_quantity=system_qty,
            counted_quantity=payload.counted_quantity,
            difference=payload.counted_quantity - system_qty,
            reason=payload.reason,
            counted_by=current_user.id
        )
        db.add(item)
    if count.status == CountStatus.DRAFT:
        count.status = CountStatus.IN_PROGRESS
    db.flush()
    add_audit_log(
        db, user_id=current_user.id, action="UPDATE" if old_values else "CREATE",
        entity_type="inventory_count_item", entity_id=item.id, old_values=old_values,
        new_values={"count_id": count.id, "product_id": item.product_id, "batch_id": item.batch_id, "counted_quantity": item.counted_quantity, "difference": item.difference},
        details=f"Zapisano pozycję inwentaryzacji {count.count_number}",
    )
    db.commit()
    db.refresh(item)
    out = CountItemOut.model_validate(item)
    prod = db.query(Product).filter(Product.id == payload.product_id).first()
    out.product_name = prod.name if prod else "Unknown"
    return out


@router.delete("/{count_id}/items/{item_id}")
def delete_item(count_id: int, item_id: int, db: Session = Depends(get_db), current_user = Depends(require_permission("counts:write"))):
    count = db.query(InventoryCount).filter(InventoryCount.id == count_id).first()
    if not count:
        raise HTTPException(status_code=404, detail="Nie znaleziono inwentaryzacji")
    if count.status == CountStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="Nie można cofnąć pozycji zakończonej inwentaryzacji")
    item = db.query(InventoryCountItem).filter(InventoryCountItem.id == item_id, InventoryCountItem.count_id == count.id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Nie znaleziono pozycji")
    old_values = {"count_id": count.id, "product_id": item.product_id, "batch_id": item.batch_id, "counted_quantity": item.counted_quantity, "difference": item.difference}
    db.delete(item)
    add_audit_log(
        db, user_id=current_user.id, action="DELETE", entity_type="inventory_count_item",
        entity_id=item.id, old_values=old_values, details=f"Cofnięto pozycję inwentaryzacji {count.count_number}",
    )
    db.commit()
    return {"message": "Pozycja została cofnięta", "item_id": item_id}

@router.post("/{count_id}/complete")
def complete_count(count_id: int, db: Session = Depends(get_db), current_user = Depends(require_permission("counts:write"))):
    count = db.query(InventoryCount).filter(InventoryCount.id == count_id).first()
    if not count:
        raise HTTPException(status_code=404, detail="Not found")
    if count.status == CountStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="Inwentaryzacja została już zakończona")
    
    # Apply differences as stock movements
    for item in count.items:
        if item.difference != 0:
            # Adjust batches - for simplicity adjust oldest batch or create adjustment
            if item.difference < 0:
                # Need to remove stock - FEFO
                remaining = abs(item.difference)
                batches_query = db.query(Batch).filter(Batch.product_id == item.product_id, Batch.quantity_available > 0)
                if count.location_id:
                    batches_query = batches_query.filter(Batch.warehouse_location_id == count.location_id)
                batches = batches_query.order_by(Batch.expiry_date.asc().nulls_last()).all()
                for b in batches:
                    if remaining <= 0:
                        break
                    take = min(remaining, b.quantity_available)
                    b.quantity_available -= take
                    remaining -= take
                    # The aggregated stock row must move with the batch, otherwise
                    # /stock and /stock/summary drift away from the batch ledger.
                    _apply_stock_delta(db, item.product_id, b.warehouse_location_id, -take)

                    mov = StockMovement(
                        product_id=item.product_id,
                        batch_id=b.id,
                        quantity=-take,
                        movement_type=MovementType.INVENTORY_ADJUSTMENT,
                        source_location_id=b.warehouse_location_id,
                        user_id=current_user.id,
                        reason=f"Inwentaryzacja {count.count_number}: {item.reason or 'korekta'}",
                        reference_id=str(count.id),
                        reference_type="inventory_count"
                    )
                    db.add(mov)
                if remaining > 0:
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            f"Nie można skorygować produktu {item.product_id} o {item.difference}: "
                            f"w partii brakuje {remaining} sztuk"
                        ),
                    )
            else:
                # Add stock - create or update batch if exists, else need to handle
                # For simplicity, add to a batch without expiry or create new
                batch_query = db.query(Batch).filter(Batch.product_id == item.product_id)
                if count.location_id:
                    batch_query = batch_query.filter(Batch.warehouse_location_id == count.location_id)
                batch = batch_query.order_by(Batch.expiry_date.desc().nulls_last()).first()
                if batch:
                    batch.quantity_available += item.difference
                    batch.quantity_received += item.difference
                else:
                    # Create new batch with no expiry
                    new_batch = Batch(
                        product_id=item.product_id,
                        batch_number=f"INV-{count.count_number}",
                        quantity_received=item.difference,
                        quantity_available=item.difference,
                        purchase_price=_product_purchase_price(db, item.product_id),
                        warehouse_location_id=count.location_id
                    )
                    db.add(new_batch)
                    db.flush()
                    batch = new_batch

                _apply_stock_delta(db, item.product_id, batch.warehouse_location_id, item.difference)

                mov = StockMovement(
                    product_id=item.product_id,
                    batch_id=batch.id if batch else None,
                    quantity=item.difference,
                    movement_type=MovementType.INVENTORY_ADJUSTMENT,
                    destination_location_id=batch.warehouse_location_id,
                    user_id=current_user.id,
                    reason=f"Inwentaryzacja {count.count_number}: nadwyżka",
                    reference_id=str(count.id),
                    reference_type="inventory_count"
                )
                db.add(mov)
    
    count.status = CountStatus.COMPLETED
    count.completed_at = datetime.utcnow()
    add_audit_log(
        db, user_id=current_user.id, action="COMPLETE", entity_type="inventory_count", entity_id=count.id,
        new_values={"count_number": count.count_number, "adjustments": [{"product_id": item.product_id, "system_quantity": item.system_quantity, "counted_quantity": item.counted_quantity, "difference": item.difference} for item in count.items]},
        details="Zakończono inwentaryzację i skorygowano stany magazynowe",
    )
    db.commit()
    
    return {"message": "Inwentaryzacja zakończona", "differences": len([i for i in count.items if i.difference != 0])}

@router.get("/{count_id}", response_model=CountOut)
def get_count(count_id: int, db: Session = Depends(get_db), current_user = Depends(require_permission("counts:read"))):
    c = db.query(InventoryCount).filter(InventoryCount.id == count_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Not found")
    out = CountOut.model_validate(c)
    out.items = []
    for item in c.items:
        item_out = CountItemOut.model_validate(item)
        prod = db.query(Product).filter(Product.id == item.product_id).first()
        item_out.product_name = prod.name if prod else "Unknown"
        out.items.append(item_out)
    return out
