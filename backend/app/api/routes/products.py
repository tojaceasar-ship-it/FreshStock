from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from typing import List, Optional
from decimal import Decimal
from app.core.database import get_db
from app.core.deps import get_current_user, require_permission
from app.models.product import Product, ProductSupplier
from app.models.batch import Batch
from app.models.stock import Stock
from app.models.category import Category
from app.schemas.product import ProductCreate, ProductUpdate, ProductOut
from app.services.audit import add_audit_log
from app.services.plans import PlanService

router = APIRouter()

@router.get("", response_model=List[ProductOut])
def list_products(
    response: Response,
    search: Optional[str] = None,
    category_id: Optional[int] = None,
    is_active: Optional[bool] = None,
    low_stock: Optional[bool] = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    stock_totals = (
        db.query(Batch.product_id.label("product_id"), func.sum(Batch.quantity_available).label("total_stock"))
        .group_by(Batch.product_id)
        .subquery()
    )
    total_stock = func.coalesce(stock_totals.c.total_stock, 0)
    q = (
        db.query(Product, total_stock.label("total_stock"), Category.name.label("category_name"))
        .outerjoin(stock_totals, stock_totals.c.product_id == Product.id)
        .outerjoin(Category, Category.id == Product.category_id)
    )
    if search:
        q = q.filter(or_(Product.name.ilike(f"%{search}%"), Product.sku.ilike(f"%{search}%"), Product.ean.ilike(f"%{search}%"), Product.brand.ilike(f"%{search}%")))
    if category_id:
        q = q.filter(Product.category_id == category_id)
    if is_active is not None:
        q = q.filter(Product.is_active == is_active)
    if low_stock:
        q = q.filter(total_stock < Product.min_stock)

    total = q.count()
    response.headers["X-Total-Count"] = str(total)
    products = q.order_by(Product.name, Product.id).offset(offset).limit(limit).all()
    result = []
    for p, product_stock, category_name in products:
        out = ProductOut.model_validate(p)
        out.total_stock = product_stock or Decimal("0")
        out.category_name = category_name
        result.append(out)
    return result

@router.get("/{product_id}", response_model=ProductOut)
def get_product(product_id: int, db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    p = db.query(Product).filter(Product.id == product_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Not found")
    total_stock = db.query(func.coalesce(func.sum(Batch.quantity_available), 0)).filter(Batch.product_id == p.id).scalar()
    out = ProductOut.model_validate(p)
    out.total_stock = total_stock or Decimal("0")
    if p.category_id:
        cat = db.query(Category).filter(Category.id == p.category_id).first()
        out.category_name = cat.name if cat else None
    return out

@router.get("/ean/{ean}", response_model=ProductOut)
def get_by_ean(ean: str, db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    p = db.query(Product).filter(Product.ean == ean).first()
    if not p:
        raise HTTPException(status_code=404, detail="Produkt nie znaleziony")
    total_stock = db.query(func.coalesce(func.sum(Batch.quantity_available), 0)).filter(Batch.product_id == p.id).scalar()
    out = ProductOut.model_validate(p)
    out.total_stock = total_stock or Decimal("0")
    return out

@router.get("/barcode/{ean}")
def barcode_lookup(ean: str, db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    """
    Lookup a product by EAN barcode.
    1. Checks local database first.
    2. If not found, queries Open Food Facts (free, global food database).
    Returns source: 'local' | 'open_food_facts' | 'not_found'
    """
    import httpx
    query = ean.strip()

    # 1. Check local DB
    p = db.query(Product).filter(or_(Product.ean == query, Product.sku == query)).first()
    if p:
        total_stock = db.query(func.coalesce(func.sum(Batch.quantity_available), 0)).filter(Batch.product_id == p.id).scalar()
        out = ProductOut.model_validate(p)
        out.total_stock = total_stock or Decimal("0")
        return {
            "source": "local",
            "found": True,
            "product": out,
        }

    internet_code = "".join(char for char in query if char.isdigit())
    if internet_code != query or len(internet_code) not in range(7, 15):
        return {"source": "not_found", "found": False, "product": None, "suggestion": {"ean": query}}

    # Query all official Open Facts product databases through API v2.
    try:
        fields = ",".join([
            "code", "product_type", "product_name_pl", "product_name", "product_name_en",
            "generic_name_pl", "generic_name", "abbreviated_product_name", "brands", "quantity",
            "image_front_url", "image_front_small_url", "image_url", "categories",
            "ingredients_text_pl", "ingredients_text", "countries_tags", "last_modified_t",
        ])
        response = httpx.get(
            f"https://world.openfoodfacts.org/api/v2/product/{internet_code}.json",
            params={"product_type": "all", "cc": "pl", "lc": "pl", "fields": fields},
            timeout=10.0,
            follow_redirects=True,
            headers={"User-Agent": "FreshStock/1.0 (https://freshstock-app.vercel.app; product lookup)"}
        )
        response.raise_for_status()
        data = response.json()
        if data.get("status") == 1 and data.get("product"):
            p_data = data["product"]
            name = (
                p_data.get("product_name_pl")
                or p_data.get("product_name")
                or p_data.get("product_name_en")
                or p_data.get("generic_name_pl")
                or p_data.get("generic_name")
                or p_data.get("abbreviated_product_name")
            )
            brand = p_data.get("brands", "").split(",")[0].strip()
            quantity = p_data.get("quantity", "")
            image_url = p_data.get("image_front_url") or p_data.get("image_front_small_url") or p_data.get("image_url")
            categories = p_data.get("categories", "")
            ingredients = p_data.get("ingredients_text_pl") or p_data.get("ingredients_text", "")

            if not name and not brand:
                return {"source": "not_found", "found": False, "product": None, "suggestion": {"ean": internet_code}}
            return {
                "source": "open_food_facts",
                "found": True,
                "product": None,
                "suggestion": {
                    "ean": data.get("code") or internet_code,
                    "name": name or f"{brand} {quantity}".strip(),
                    "brand": brand,
                    "quantity": quantity,
                    "image_url": image_url,
                    "categories_raw": categories,
                    "ingredients": ingredients[:300] if ingredients else "",
                    "product_type": p_data.get("product_type") or "food",
                    "source_url": str(response.url),
                }
            }
    except (httpx.HTTPError, ValueError):
        pass

    # 3. Not found anywhere
    return {
        "source": "not_found",
        "found": False,
        "product": None,
        "suggestion": {"ean": internet_code or query}
    }


@router.post("", response_model=ProductOut)
def create_product(payload: ProductCreate, db: Session = Depends(get_db), current_user = Depends(require_permission("products:write"))):
    PlanService.assert_limit(db, current_user.tenant_id, "sku")
    if db.query(Product).filter(Product.sku == payload.sku).first():
        raise HTTPException(status_code=400, detail="SKU już istnieje")
    if payload.ean and db.query(Product).filter(Product.ean == payload.ean).first():
        raise HTTPException(status_code=400, detail="EAN już istnieje")
    prod = Product(**payload.model_dump())
    db.add(prod)
    db.flush()
    add_audit_log(db, user_id=current_user.id, action="CREATE", entity_type="product", entity_id=prod.id, new_values=payload.model_dump(), details="Utworzono produkt")
    db.commit()
    db.refresh(prod)
    out = ProductOut.model_validate(prod)
    out.total_stock = 0
    return out

@router.put("/{product_id}", response_model=ProductOut)
def update_product(product_id: int, payload: ProductUpdate, db: Session = Depends(get_db), current_user = Depends(require_permission("products:write"))):
    prod = db.query(Product).filter(Product.id == product_id).first()
    if not prod:
        raise HTTPException(status_code=404, detail="Not found")
    data = payload.model_dump(exclude_unset=True)
    old_values = {key: getattr(prod, key) for key in data}
    if "sku" in data and data["sku"] != prod.sku:
        if db.query(Product).filter(Product.sku == data["sku"]).first():
            raise HTTPException(status_code=400, detail="SKU już istnieje")
    if "ean" in data and data["ean"]:
        existing = db.query(Product).filter(Product.ean == data["ean"], Product.id != product_id).first()
        if existing:
            raise HTTPException(status_code=400, detail="EAN już istnieje")
    for k, v in data.items():
        setattr(prod, k, v)
    add_audit_log(db, user_id=current_user.id, action="UPDATE", entity_type="product", entity_id=prod.id, old_values=old_values, new_values=data, details="Zmieniono dane produktu, w tym ceny lub parametry stanu")
    db.commit()
    db.refresh(prod)
    total_stock = db.query(func.coalesce(func.sum(Batch.quantity_available), 0)).filter(Batch.product_id == prod.id).scalar()
    out = ProductOut.model_validate(prod)
    out.total_stock = total_stock or Decimal("0")
    return out

@router.delete("/{product_id}")
def delete_product(product_id: int, db: Session = Depends(get_db), current_user = Depends(require_permission("products:write"))):
    prod = db.query(Product).filter(Product.id == product_id).first()
    if not prod:
        raise HTTPException(status_code=404, detail="Not found")
    # check if has stock
    stock = db.query(func.sum(Batch.quantity_available)).filter(Batch.product_id == product_id).scalar()
    if stock and stock > 0:
        raise HTTPException(status_code=400, detail="Nie można usunąć produktu z stanem magazynowym")
    add_audit_log(db, user_id=current_user.id, action="DELETE", entity_type="product", entity_id=prod.id, old_values={"sku": prod.sku, "name": prod.name, "purchase_price": prod.purchase_price, "selling_price": prod.selling_price})
    db.delete(prod)
    db.commit()
    return {"message": "Deleted"}

@router.get("/{product_id}/batches")
def get_product_batches(product_id: int, db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    batches = db.query(Batch).filter(Batch.product_id == product_id).order_by(Batch.expiry_date.asc().nulls_last()).all()
    return batches
