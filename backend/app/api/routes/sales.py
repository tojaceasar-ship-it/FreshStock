from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session, selectinload
from typing import List, Optional
from datetime import datetime, date
from decimal import Decimal
from app.core.database import get_db
from app.core.deps import get_current_user, require_permission
from app.models.sale import Sale, SaleItem, SaleSource
from app.models.batch import Batch
from app.models.stock import Stock
from app.models.stock_movement import StockMovement, MovementType
from app.models.product import Product
from pydantic import BaseModel, ConfigDict, Field
import csv, io
from app.services.audit import add_audit_log
from app.services.sales_engine import InsufficientStockError, SalesEngineError, SalesEngineItem, process_sale

router = APIRouter()

class SaleItemCreate(BaseModel):
    product_id: int
    quantity: Decimal = Field(gt=0, max_digits=14, decimal_places=3)
    unit_price: Optional[Decimal] = None

class SaleCreate(BaseModel):
    sale_date: Optional[datetime] = None
    source: str = "manual"
    items: List[SaleItemCreate]

class SaleItemOut(BaseModel):
    id: int
    sale_id: int
    product_id: int
    product_name: Optional[str] = None
    batch_id: Optional[int]
    quantity: Decimal
    unit_price: Decimal
    total_price: Decimal
    model_config = ConfigDict(from_attributes=True)

class SaleOut(BaseModel):
    id: int
    sale_number: str
    sale_date: datetime
    total_amount: Decimal
    source: str
    created_at: datetime
    items: List[SaleItemOut] = []
    model_config = ConfigDict(from_attributes=True)

def generate_sale_number():
    import uuid
    return f"SALE-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:10].upper()}"

@router.get("", response_model=List[SaleOut])
def list_sales(limit: int = 100, db: Session = Depends(get_db), current_user = Depends(require_permission("sales:read"))):
    tenant_id = int(getattr(current_user, "tenant_id", 1))
    sales = (
        db.query(Sale)
        .options(selectinload(Sale.items).selectinload(SaleItem.product))
        .filter(Sale.tenant_id == tenant_id)
        .order_by(Sale.sale_date.desc())
        .limit(limit)
        .all()
    )
    result = []
    for s in sales:
        out = SaleOut.model_validate(s)
        out.items = []
        for item in s.items:
            item_out = SaleItemOut.model_validate(item)
            item_out.product_name = item.product.name if item.product else "Unknown"
            out.items.append(item_out)
        result.append(out)
    return result

@router.post("", response_model=SaleOut)
def create_sale(payload: SaleCreate, db: Session = Depends(get_db), current_user = Depends(require_permission("sales:create"))):
    try:
        sale, _ = process_sale(
            db,
            sale_number=generate_sale_number(),
            sale_date=payload.sale_date,
            source=payload.source,
            user_id=current_user.id,
            items=[SalesEngineItem(product_id=item.product_id, quantity=item.quantity, unit_price=item.unit_price) for item in payload.items],
        )
        add_audit_log(
            db, user_id=current_user.id, action="CREATE", entity_type="sale", entity_id=sale.id,
            new_values={"sale_number": sale.sale_number, "total_amount": sale.total_amount, "items": [{"product_id": item.product_id, "quantity": item.quantity, "unit_price": item.unit_price} for item in payload.items]},
            details="Zarejestrowano sprzedaż i rozchód partii według FEFO",
        )
        db.commit()
        db.refresh(sale)
        
        out = SaleOut.model_validate(sale)
        out.items = []
        for item in sale.items:
            item_out = SaleItemOut.model_validate(item)
            prod = db.query(Product).filter(Product.id == item.product_id).first()
            item_out.product_name = prod.name if prod else "Unknown"
            out.items.append(item_out)
        return out
        
    except InsufficientStockError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc))
    except SalesEngineError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/import/csv")
def import_csv(file: UploadFile = File(...), db: Session = Depends(get_db), current_user = Depends(require_permission("sales:import"))):
    content = file.file.read().decode('utf-8')
    reader = csv.DictReader(io.StringIO(content))
    created = 0
    errors = []
    
    for row_num, row in enumerate(reader, start=2):
        try:
            # Expected columns: product_sku or ean, quantity, unit_price, sale_date
            sku = row.get('sku') or row.get('product_sku') or row.get('ean')
            qty = Decimal(row.get('quantity', '0') or '0')
            price = Decimal(row.get('unit_price', '0') or '0')
            
            if not sku or qty <= 0:
                errors.append(f"Wiersz {row_num}: brak SKU lub ilości")
                continue
            
            product = db.query(Product).filter((Product.sku == sku) | (Product.ean == sku)).first()
            if not product:
                errors.append(f"Wiersz {row_num}: produkt {sku} nie znaleziony")
                continue
            
            if price == 0:
                price = product.selling_price
            
            process_sale(
                db, sale_number=generate_sale_number(), sale_date=datetime.utcnow(),
                source=SaleSource.CSV, user_id=current_user.id,
                items=[SalesEngineItem(product_id=product.id, quantity=qty, unit_price=price)],
            )
            created += 1
            
        except Exception as e:
            errors.append(f"Wiersz {row_num}: {str(e)}")
    
    db.commit()
    return {"created": created, "errors": errors}

@router.get("/{sale_id}", response_model=SaleOut)
def get_sale(sale_id: int, db: Session = Depends(get_db), current_user = Depends(require_permission("sales:read"))):
    tenant_id = int(getattr(current_user, "tenant_id", 1))
    s = (
        db.query(Sale)
        .options(selectinload(Sale.items).selectinload(SaleItem.product))
        .filter(Sale.id == sale_id, Sale.tenant_id == tenant_id)
        .first()
    )
    if not s:
        raise HTTPException(status_code=404, detail="Not found")
    out = SaleOut.model_validate(s)
    out.items = []
    for item in s.items:
        item_out = SaleItemOut.model_validate(item)
        item_out.product_name = item.product.name if item.product else "Unknown"
        out.items.append(item_out)
    return out
