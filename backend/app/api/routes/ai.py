from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from collections import defaultdict
from datetime import datetime, timedelta, date
from app.core.database import get_db
from app.core.deps import get_current_user, require_permission
from app.models.product import Product
from app.models.batch import Batch
from app.models.sale import Sale, SaleItem
from app.models.waste import Waste
from pydantic import BaseModel

from app.services.plans import require_feature
router = APIRouter(dependencies=[Depends(require_feature("ai_restock"))])

class AIInsight(BaseModel):
    type: str
    severity: str
    title: str
    message: str
    product_id: Optional[int] = None
    product_name: Optional[str] = None
    action: Optional[str] = None
    data: Optional[dict] = None

@router.post("/insights", response_model=List[AIInsight])
def get_insights(db: Session = Depends(get_db), current_user = Depends(require_permission("inventory:read"))):
    insights = []
    today = date.today()
    products = db.query(Product).filter(Product.is_active == True).all()
    product_ids = [product.id for product in products]
    stock_by_product = dict(db.query(
        Batch.product_id, func.coalesce(func.sum(Batch.quantity_available), 0),
    ).filter(Batch.product_id.in_(product_ids)).group_by(Batch.product_id).all()) if product_ids else {}
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    sales_by_product = dict(db.query(
        SaleItem.product_id, func.coalesce(func.sum(SaleItem.quantity), 0),
    ).join(Sale).filter(
        SaleItem.product_id.in_(product_ids), Sale.sale_date >= thirty_days_ago,
    ).group_by(SaleItem.product_id).all()) if product_ids else {}
    expiring_by_product = defaultdict(list)
    if product_ids:
        for batch in db.query(Batch).filter(
            Batch.product_id.in_(product_ids), Batch.quantity_available > 0,
            Batch.expiry_date.isnot(None), Batch.expiry_date <= today + timedelta(days=7),
            Batch.expiry_date >= today,
        ).all():
            expiring_by_product[batch.product_id].append(batch)
    
    for product in products:
        total_stock = float(stock_by_product.get(product.id, 0) or 0)
        sales_qty = sales_by_product.get(product.id, 0) or 0
        
        avg_daily = float(sales_qty) / 30 if sales_qty else 0
        
        # Stockout prediction
        if avg_daily > 0 and total_stock > 0:
            days_until = total_stock / avg_daily
            if days_until <= 2:
                insights.append(AIInsight(
                    type="stockout_risk",
                    severity="critical",
                    title=f"{product.name} - ryzyko braku towaru",
                    message=f"{product.name} sprzedaje się średnio {avg_daily:.1f} sztuk dziennie. Aktualny stan wynosi {total_stock} sztuk. Przy obecnym tempie produkt skończy się za {days_until:.0f} dni. Zalecane zamówienie: {product.target_stock - total_stock} sztuk.",
                    product_id=product.id,
                    product_name=product.name,
                    action="order",
                    data={"current_stock": int(total_stock), "avg_daily": round(avg_daily,2), "days_until": round(days_until,1), "suggested_order": int(product.target_stock - total_stock)}
                ))
        
        # Expiry waste prediction
        for batch in expiring_by_product.get(product.id, []):
            days_until_exp = (batch.expiry_date - today).days
            # Estimate how many will be sold before expiry
            expected_sales_before_expiry = avg_daily * days_until_exp if avg_daily > 0 else 0
            likely_waste = max(0, float(batch.quantity_available) - expected_sales_before_expiry)
            
            if likely_waste > 0 and batch.quantity_available > 3:
                discount = 50 if days_until_exp <= 1 else 25 if days_until_exp <= 3 else 10
                insights.append(AIInsight(
                    type="expiry_waste",
                    severity="high" if days_until_exp <= 2 else "medium",
                    title=f"{product.name} - ryzyko strat",
                    message=f"{batch.quantity_available} sztuk {product.name} kończy termin za {days_until_exp} dni. Przy obecnym tempie sprzedaży {avg_daily:.1f} szt/dzień, około {likely_waste:.0f} sztuk prawdopodobnie pozostanie niesprzedanych. Sugeruję przecenę {discount}%.",
                    product_id=product.id,
                    product_name=product.name,
                    action="promote",
                    data={"batch_id": batch.id, "quantity": batch.quantity_available, "days_until": days_until_exp, "likely_waste": int(likely_waste), "suggested_discount": discount}
                ))
        
        # Slow mover detection
        if total_stock > float(product.target_stock) * 1.5 and avg_daily < 0.5 and total_stock > 10:
            insights.append(AIInsight(
                type="slow_mover",
                severity="low",
                title=f"{product.name} - wolna rotacja",
                message=f"{product.name} ma wysoki stan {total_stock} szt przy niskiej sprzedaży {avg_daily:.1f} szt/dzień. Warto rozważyć zmniejszenie zamówień lub promocję.",
                product_id=product.id,
                product_name=product.name,
                action="review",
                data={"current_stock": int(total_stock), "target": product.target_stock, "avg_daily": avg_daily}
            ))
    
    # Waste pattern insights
    week_ago = datetime.utcnow() - timedelta(days=7)
    waste_by_product = db.query(Waste.product_id, func.sum(Waste.quantity), func.sum(Waste.purchase_value)).filter(Waste.created_at >= week_ago).group_by(Waste.product_id).order_by(func.sum(Waste.purchase_value).desc()).limit(3).all()
    
    for product_id, qty, value in waste_by_product:
        product = db.query(Product).filter(Product.id == product_id).first()
        if product and float(value) > 20:
            insights.append(AIInsight(
                type="high_waste",
                severity="medium",
                title=f"Wysokie straty: {product.name}",
                message=f"W ostatnim tygodniu straty dla {product.name} wyniosły {qty} sztuk o wartości {float(value):.2f} zł. Sprawdź przyczyny i rozważ korektę zamówień.",
                product_id=product.id,
                product_name=product.name,
                action="investigate",
                data={"waste_qty": int(qty), "waste_value": float(value)}
            ))
    
    # Sort by severity
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    insights.sort(key=lambda x: severity_order.get(x.severity, 4))
    
    return insights[:20]

@router.get("/product/{product_id}")
def product_insight(product_id: int, db: Session = Depends(get_db), current_user = Depends(require_permission("products:read"))):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        return {"error": "Product not found"}
    
    total_stock = db.query(func.coalesce(func.sum(Batch.quantity_available), 0)).filter(Batch.product_id == product_id).scalar() or 0
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    sales_qty = db.query(func.coalesce(func.sum(SaleItem.quantity), 0)).join(Sale).filter(SaleItem.product_id == product_id, Sale.sale_date >= thirty_days_ago).scalar() or 0
    avg_daily = float(sales_qty) / 30 if sales_qty else 0
    
    batches = db.query(Batch).filter(Batch.product_id == product_id, Batch.quantity_available > 0).order_by(Batch.expiry_date.asc().nulls_last()).all()
    
    insights = []
    if avg_daily > 0:
        days_until = total_stock / avg_daily if total_stock > 0 else 0
        insights.append(f"Sprzedaje się średnio {avg_daily:.1f} sztuk dziennie.")
        insights.append(f"Aktualny stan {total_stock} sztuk wystarczy na {days_until:.1f} dni.")
        if days_until < 3:
            insights.append(f"Zalecane zamówienie: {product.target_stock - total_stock} sztuk.")
    
    for b in batches:
        if b.expiry_date:
            days = (b.expiry_date - date.today()).days
            if days <= 7:
                insights.append(f"Partia {b.batch_number}: {b.quantity_available} szt, termin {b.expiry_date} (za {days} dni).")
    
    return {
        "product_id": product.id,
        "product_name": product.name,
        "current_stock": int(total_stock),
        "avg_daily_sales": round(avg_daily, 2),
        "insights": insights,
        "batches": [{"batch_number": b.batch_number, "quantity": b.quantity_available, "expiry": b.expiry_date.isoformat() if b.expiry_date else None} for b in batches]
    }
