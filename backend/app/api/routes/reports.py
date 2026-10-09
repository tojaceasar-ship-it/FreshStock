from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional
from datetime import datetime, timedelta, date
from decimal import Decimal
from app.core.database import get_db
from app.core.deps import get_current_user, require_permission
from app.models.product import Product
from app.models.batch import Batch
from app.models.sale import Sale, SaleItem
from app.models.waste import Waste
from app.models.delivery import Delivery
from app.models.category import Category
from app.models.supplier import Supplier

router = APIRouter()

@router.get("/sales")
def sales_report(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    category_id: Optional[int] = None,
    product_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user = Depends(require_permission("reports:read"))
):
    if not date_from:
        date_from = date.today() - timedelta(days=30)
    if not date_to:
        date_to = date.today()
    
    q = db.query(SaleItem).join(Sale).join(Product, SaleItem.product_id == Product.id)
    q = q.filter(Sale.sale_date >= datetime.combine(date_from, datetime.min.time()),
                 Sale.sale_date <= datetime.combine(date_to, datetime.max.time()))
    
    if product_id:
        q = q.filter(SaleItem.product_id == product_id)
    if category_id:
        q = q.filter(Product.category_id == category_id)
    
    items = q.all()
    
    total_qty = sum((i.quantity for i in items), Decimal("0"))
    total_value = sum((i.total_price for i in items), Decimal("0"))
    
    # Group by product
    by_product = {}
    for item in items:
        prod = db.query(Product).filter(Product.id == item.product_id).first()
        if not prod:
            continue
        if prod.id not in by_product:
            by_product[prod.id] = {"product_id": prod.id, "product_name": prod.name, "sku": prod.sku, "quantity": Decimal("0"), "value": Decimal("0"), "margin": Decimal("0")}
        by_product[prod.id]["quantity"] += item.quantity
        by_product[prod.id]["value"] += item.total_price
        cost = prod.purchase_price * item.quantity
        by_product[prod.id]["margin"] += item.total_price - cost
    
    return {
        "period": {"from": date_from.isoformat(), "to": date_to.isoformat()},
        "total_quantity": total_qty,
        "total_value": total_value,
        "by_product": list(by_product.values())
    }

@router.get("/waste")
def waste_report(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    db: Session = Depends(get_db),
    current_user = Depends(require_permission("reports:read"))
):
    if not date_from:
        date_from = date.today() - timedelta(days=30)
    if not date_to:
        date_to = date.today()
    
    q = db.query(Waste).filter(Waste.created_at >= datetime.combine(date_from, datetime.min.time()),
                               Waste.created_at <= datetime.combine(date_to, datetime.max.time()))
    wastes = q.all()
    
    total_value = sum((w.purchase_value for w in wastes), Decimal("0"))
    total_sale_value = sum((w.sale_value for w in wastes), Decimal("0"))
    
    by_reason = {}
    by_product = {}
    
    for w in wastes:
        reason = w.reason.value if hasattr(w.reason, 'value') else str(w.reason)
        if reason not in by_reason:
            by_reason[reason] = {"reason": reason, "count": 0, "value": 0}
        by_reason[reason]["count"] += 1
        by_reason[reason]["value"] += float(w.purchase_value)
        
        prod = db.query(Product).filter(Product.id == w.product_id).first()
        if prod:
            if prod.id not in by_product:
                by_product[prod.id] = {"product_id": prod.id, "product_name": prod.name, "quantity": Decimal("0"), "value": Decimal("0")}
            by_product[prod.id]["quantity"] += w.quantity
            by_product[prod.id]["value"] += w.purchase_value
    
    return {
        "period": {"from": date_from.isoformat(), "to": date_to.isoformat()},
        "total_value": total_value,
        "total_sale_value": total_sale_value,
        "by_reason": list(by_reason.values()),
        "by_product": list(by_product.values())
    }

@router.get("/inventory-value")
def inventory_value(db: Session = Depends(get_db), current_user = Depends(require_permission("reports:read"))):
    cost_value = func.sum(func.coalesce(Batch.purchase_price, Product.purchase_price) * Batch.quantity_available)
    retail_value = func.sum(Product.selling_price * Batch.quantity_available)
    rows = (
        db.query(
            func.coalesce(Category.name, "Bez kategorii").label("category"),
            func.coalesce(cost_value, 0).label("cost_value"),
            func.coalesce(retail_value, 0).label("retail_value"),
            func.coalesce(func.sum(Batch.quantity_available), 0).label("quantity"),
        )
        .join(Product, Product.id == Batch.product_id)
        .outerjoin(Category, Category.id == Product.category_id)
        .filter(Batch.quantity_available > 0)
        .group_by(Category.name)
        .all()
    )
    by_category = [
        {"category": row.category, "cost_value": row.cost_value, "retail_value": row.retail_value, "quantity": row.quantity}
        for row in rows
    ]
    total_cost = sum((Decimal(row.cost_value) for row in rows), Decimal("0"))
    total_retail = sum((Decimal(row.retail_value) for row in rows), Decimal("0"))
    return {
        "total_cost_value": total_cost,
        "total_retail_value": total_retail,
        "potential_margin": total_retail - total_cost,
        "by_category": by_category
    }

@router.get("/rotation")
def rotation_report(db: Session = Depends(get_db), current_user = Depends(require_permission("reports:read"))):
    products = db.query(Product).filter(Product.is_active == True).all()
    result = []
    
    for prod in products:
        total_stock = db.query(func.coalesce(func.sum(Batch.quantity_available), 0)).filter(Batch.product_id == prod.id).scalar() or 0
        
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        sales_qty = db.query(func.coalesce(func.sum(SaleItem.quantity), 0)).join(Sale).filter(
            SaleItem.product_id == prod.id,
            Sale.sale_date >= thirty_days_ago
        ).scalar() or 0
        
        avg_daily = float(sales_qty) / 30 if sales_qty else 0
        days_until_stockout = float(total_stock) / avg_daily if avg_daily > 0 else 999
        stock_turnover = float(sales_qty) / float(total_stock) if total_stock > 0 else 0
        days_of_inventory = 30 / stock_turnover if stock_turnover > 0 else 999
        
        result.append({
            "product_id": prod.id,
            "product_name": prod.name,
            "sku": prod.sku,
            "current_stock": total_stock,
            "avg_daily_sales": round(avg_daily, 2),
            "days_until_stockout": round(days_until_stockout, 1) if days_until_stockout < 999 else None,
            "stock_turnover": round(stock_turnover, 2),
            "days_of_inventory": round(days_of_inventory, 1) if days_of_inventory < 999 else None,
            "sales_velocity": round(avg_daily, 2)
        })
    
    return sorted(result, key=lambda x: x["avg_daily_sales"], reverse=True)

@router.get("/suppliers")
def supplier_report(db: Session = Depends(get_db), current_user = Depends(require_permission("reports:read"))):
    suppliers = db.query(Supplier).all()
    result = []
    for sup in suppliers:
        deliveries = db.query(Delivery).filter(Delivery.supplier_id == sup.id).all()
        total_value = sum(float(d.total_value) for d in deliveries)
        result.append({
            "supplier_id": sup.id,
            "supplier_name": sup.name,
            "delivery_count": len(deliveries),
            "total_value": total_value,
            "avg_delivery_value": total_value / len(deliveries) if deliveries else 0
        })
    return sorted(result, key=lambda x: x["total_value"], reverse=True)
