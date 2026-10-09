from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_permission
from app.models.batch import Batch
from app.models.delivery import Delivery
from app.models.product import Product
from app.models.sale import SaleItem
from app.models.supplier import Supplier
from app.models.waste import Waste
from app.models.stock_movement import StockMovement

router = APIRouter()


def _batch_lineage(batch: Batch, db: Session) -> dict:
    product = db.query(Product).filter(Product.id == batch.product_id).first()
    supplier = db.query(Supplier).filter(Supplier.id == batch.supplier_id).first() if batch.supplier_id else None
    delivery = db.query(Delivery).filter(Delivery.id == batch.delivery_id).first() if batch.delivery_id else None
    sales = db.query(SaleItem).filter(SaleItem.batch_id == batch.id).all()
    waste_ids = [
        int(value) for (value,) in db.query(StockMovement.reference_id).filter(
            StockMovement.batch_id == batch.id,
            StockMovement.reference_type == "waste",
            StockMovement.reference_id.isnot(None),
        ).all() if str(value).isdigit()
    ]
    waste_query = db.query(Waste).filter(Waste.batch_id == batch.id)
    if waste_ids:
        waste_query = db.query(Waste).filter((Waste.batch_id == batch.id) | (Waste.id.in_(waste_ids)))
    wastes = waste_query.distinct().all()
    sold_quantity = sum(item.quantity for item in sales)
    wasted_quantity = sum(item.quantity for item in wastes)
    return {
        "batch": {
            "id": batch.id,
            "batch_number": batch.batch_number,
            "product_id": batch.product_id,
            "product_name": product.name if product else None,
            "expiry_date": batch.expiry_date,
            "quantity_received": batch.quantity_received,
            "quantity_available": batch.quantity_available,
        },
        "supplier": {"id": supplier.id, "name": supplier.name} if supplier else None,
        "delivery": {
            "id": delivery.id,
            "document_number": delivery.document_number,
            "delivered_at": delivery.delivered_at,
        } if delivery else None,
        "sales": [{
            "sale_id": item.sale_id,
            "sale_number": item.sale.sale_number if item.sale else None,
            "sale_date": item.sale.sale_date if item.sale else None,
            "quantity": item.quantity,
            "unit_price": float(item.unit_price),
        } for item in sales],
        "waste": [{
            "id": item.id,
            "quantity": item.quantity,
            "reason": item.reason.value if hasattr(item.reason, "value") else str(item.reason),
            "created_at": item.created_at,
        } for item in wastes],
        "summary": {
            "received": batch.quantity_received,
            "sold": sold_quantity,
            "wasted": wasted_quantity,
            "available": batch.quantity_available,
        },
    }


@router.get("/batches/{batch_id}")
def batch_traceability(batch_id: int, db: Session = Depends(get_db), current_user=Depends(require_permission("products:read"))):
    batch = db.query(Batch).filter(Batch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Partia nie istnieje")
    return _batch_lineage(batch, db)


@router.get("/products/{product_id}")
def product_traceability(product_id: int, db: Session = Depends(get_db), current_user=Depends(require_permission("products:read"))):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Produkt nie istnieje")
    batches = db.query(Batch).filter(Batch.product_id == product_id).order_by(Batch.created_at.desc()).all()
    return {"product": {"id": product.id, "sku": product.sku, "name": product.name}, "batches": [_batch_lineage(batch, db) for batch in batches]}
