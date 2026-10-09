from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, date, timedelta
from app.core.database import get_db
from app.core.deps import get_current_user, require_permission
from app.models.product import Product
from app.models.batch import Batch
from app.models.alert import Alert
from app.models.sale import Sale, SaleItem
from app.models.waste import Waste
from app.models.delivery import Delivery
from app.models.stock_movement import StockMovement
from app.models.onboarding import StoreSettings

router = APIRouter()

@router.get("")
def get_dashboard(db: Session = Depends(get_db), current_user = Depends(require_permission("dashboard:read"))):
    today = date.today()
    today_start = datetime.combine(today, datetime.min.time())
    
    # Get store settings for expiry rules
    store = db.query(StoreSettings).filter_by(tenant_id=current_user.tenant_id).first()
    expiry_rules = sorted(set(int(x) for x in (store.expiry_rules if store else [7, 3, 1]) if int(x) >= 0), reverse=True) if store else [7, 3, 1]
    
    stock_totals = db.query(
        Batch.product_id.label("product_id"),
        func.coalesce(func.sum(Batch.quantity_available), 0).label("total_stock"),
    ).group_by(Batch.product_id).subquery()
    stock_value = func.coalesce(stock_totals.c.total_stock, 0)
    
    # Expiring counts
    expired_count = db.query(func.count(Batch.id)).filter(Batch.expiry_date < today, Batch.quantity_available > 0).scalar() or 0
    today_expiring = db.query(func.count(Batch.id)).filter(Batch.expiry_date == today, Batch.quantity_available > 0).scalar() or 0
    
    # Use expiry rules for 3 and 7 days (or configured values)
    three_days_threshold = today + timedelta(days=3)
    seven_days_threshold = today + timedelta(days=7)
    three_days = db.query(func.count(Batch.id)).filter(Batch.expiry_date <= three_days_threshold, Batch.expiry_date >= today, Batch.quantity_available > 0).scalar() or 0
    seven_days = db.query(func.count(Batch.id)).filter(Batch.expiry_date <= seven_days_threshold, Batch.expiry_date >= today, Batch.quantity_available > 0).scalar() or 0
    
    active_products = db.query(Product).filter(Product.is_active == True)
    total_sku = active_products.count()
    out_of_stock = active_products.outerjoin(stock_totals, stock_totals.c.product_id == Product.id).filter(stock_value == 0).count()
    low_stock = active_products.outerjoin(stock_totals, stock_totals.c.product_id == Product.id).filter(stock_value > 0, stock_value <= Product.min_stock).count()
    low_rows = (
        db.query(Product.id, Product.name, Product.sku, Product.min_stock, Product.target_stock, stock_value.label("current_stock"))
        .outerjoin(stock_totals, stock_totals.c.product_id == Product.id)
        .filter(Product.is_active == True, stock_value <= Product.min_stock)
        .order_by(stock_value, Product.id).limit(10).all()
    )
    low_stock_data = [{"product_id": r.id, "product_name": r.name, "sku": r.sku, "current_stock": r.current_stock, "min_stock": r.min_stock, "target_stock": r.target_stock} for r in low_rows]
    
    # Active alerts
    active_alerts = db.query(func.count(Alert.id)).filter(Alert.is_resolved == False).scalar() or 0
    critical_alerts = db.query(func.count(Alert.id)).filter(Alert.severity == "critical", Alert.is_resolved == False).scalar() or 0
    
    # Sales today
    sales_today = db.query(func.coalesce(func.sum(Sale.total_amount), 0)).filter(Sale.sale_date >= today_start).scalar() or 0
    sales_today_count = db.query(func.count(Sale.id)).filter(Sale.sale_date >= today_start).scalar() or 0
    
    # Waste today
    waste_today = db.query(func.coalesce(func.sum(Waste.purchase_value), 0)).filter(Waste.created_at >= today_start).scalar() or 0
    
    # Inventory value
    inventory_value = db.query(func.coalesce(func.sum(Batch.quantity_available * Batch.purchase_price), 0)).filter(Batch.quantity_available > 0).scalar() or 0
    
    # Financial Risk - use expiry rules from store settings
    expired_value = db.query(func.coalesce(func.sum(Batch.quantity_available * Batch.purchase_price), 0)).filter(Batch.expiry_date < today, Batch.quantity_available > 0).scalar() or 0
    today_risk = db.query(func.coalesce(func.sum(Batch.quantity_available * Batch.purchase_price), 0)).filter(Batch.expiry_date == today, Batch.quantity_available > 0).scalar() or 0
    
    # Use configured expiry rules for risk calculation
    three_days_risk = 0
    seven_days_risk = 0
    if 3 in expiry_rules:
        three_days_risk = db.query(func.coalesce(func.sum(Batch.quantity_available * Batch.purchase_price), 0)).filter(Batch.expiry_date > today, Batch.expiry_date <= today + timedelta(days=3), Batch.quantity_available > 0).scalar() or 0
    if 7 in expiry_rules:
        seven_days_risk = db.query(func.coalesce(func.sum(Batch.quantity_available * Batch.purchase_price), 0)).filter(Batch.expiry_date > today + timedelta(days=3), Batch.expiry_date <= today + timedelta(days=7), Batch.quantity_available > 0).scalar() or 0
    
    # Task Engine
    tasks = []
    if expired_count > 0:
        tasks.append({"priority": "CRITICAL", "action": f"Usuń {expired_count} przeterminowanych partii", "type": "remove_expired", "count": expired_count})
        
    if three_days > 0:
        tasks.append({"priority": "HIGH", "action": f"Przeceniaj {three_days} partii z terminem < 3 dni", "type": "markdown", "count": three_days})
        
    if out_of_stock > 0:
        tasks.append({"priority": "HIGH", "action": f"Uzupełnij {out_of_stock} braków (Out of stock)", "type": "restock", "count": out_of_stock})
        
    if active_alerts > 0:
        tasks.append({"priority": "MEDIUM", "action": f"Rozwiąż {active_alerts} alertów / różnic magazynowych", "type": "alerts", "count": active_alerts})
        
    if low_stock > 0:
        tasks.append({"priority": "MEDIUM", "action": f"Przygotuj zamówienie uzupełniające na {low_stock} produktów (Low stock)", "type": "order", "count": low_stock})
    
    # Calculate recovery rate if possible (mocked for now, as we need historical markdowns)
    # total_sales = db.query(func.coalesce(func.sum(Sale.total_amount), 0)).scalar() or 1
    # waste_ratio = (float(waste_today) / float(total_sales)) * 100 if float(total_sales) > 0 else 0
    
    # Recent deliveries
    recent_deliveries = db.query(Delivery).order_by(Delivery.created_at.desc()).limit(5).all()
    recent_deliveries_data = [{"id": d.id, "document_number": d.document_number, "supplier": d.supplier.name if d.supplier else None, "total_value": float(d.total_value), "created_at": d.created_at.isoformat() if d.created_at else None} for d in recent_deliveries]
    
    # Top sellers (last 30 days)
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    top_sellers = db.query(
        Product.id, Product.name, Product.sku,
        func.sum(SaleItem.quantity).label("total_qty"),
        func.sum(SaleItem.total_price).label("total_value")
    ).join(SaleItem, SaleItem.product_id == Product.id).join(Sale, Sale.id == SaleItem.sale_id).filter(Sale.sale_date >= thirty_days_ago).group_by(Product.id).order_by(func.sum(SaleItem.quantity).desc()).limit(5).all()
    
    top_sellers_data = [{"product_id": r[0], "product_name": r[1], "sku": r[2], "quantity": r[3], "value": float(r[4])} for r in top_sellers]
    
    # Slow movers (products with stock but no sales last 30 days)
    sold_product_ids = db.query(SaleItem.product_id).join(Sale).filter(Sale.sale_date >= thirty_days_ago)
    slow_rows = (
        db.query(Product.id, Product.name, Product.sku, stock_value.label("stock"))
        .join(stock_totals, stock_totals.c.product_id == Product.id)
        .filter(Product.is_active == True, stock_value > 0, ~Product.id.in_(sold_product_ids))
        .order_by(Product.id).limit(5).all()
    )
    slow_movers = [{"product_id": r.id, "product_name": r.name, "sku": r.sku, "stock": r.stock} for r in slow_rows]
    
    # Expiring products details
    expiring_batches = db.query(Batch, Product.name, Product.sku).join(Product, Product.id == Batch.product_id).filter(Batch.expiry_date <= today + timedelta(days=7), Batch.quantity_available > 0).order_by(Batch.expiry_date.asc()).limit(10).all()
    expiring_data = []
    for b, product_name, product_sku in expiring_batches:
        expiring_data.append({
            "batch_id": b.id,
            "product_id": b.product_id,
            "product_name": product_name,
            "sku": product_sku,
            "batch_number": b.batch_number,
            "expiry_date": b.expiry_date.isoformat() if b.expiry_date else None,
            "days_until": (b.expiry_date - today).days if b.expiry_date else None,
            "quantity": b.quantity_available
        })
    
    return {
        "requires_attention": {
            "expired": expired_count,
            "today": today_expiring,
            "in_3_days": three_days,
            "in_7_days": seven_days,
            "out_of_stock": out_of_stock,
            "low_stock": low_stock,
            "active_alerts": active_alerts,
            "critical_alerts": critical_alerts,
            "potential_loss": float(expired_value)
        },
        "financial_risk": {
            "expired": float(expired_value),
            "today": float(today_risk),
            "in_3_days": float(three_days_risk),
            "in_7_days": float(seven_days_risk),
            "total_risk": float(today_risk + three_days_risk + seven_days_risk)
        },
        "tasks": tasks,
        "kpi": {
            "sales_today": float(sales_today),
            "sales_count_today": sales_today_count,
            "waste_today": float(waste_today),
            "inventory_value": float(inventory_value),
            "total_sku": total_sku,
            "active_alerts": active_alerts
        },
        "recent_deliveries": recent_deliveries_data,
        "top_sellers": top_sellers_data,
        "slow_movers": slow_movers,
        "expiring_products": expiring_data,
        "low_stock_products": low_stock_data
    }

@router.get("/expiry")
def expiry_dashboard(db: Session = Depends(get_db), current_user = Depends(require_permission("dashboard:read"))):
    today = date.today()
    from datetime import timedelta
    
    # Get store settings for expiry rules
    store = db.query(StoreSettings).filter_by(tenant_id=current_user.tenant_id).first()
    expiry_rules = sorted(set(int(x) for x in (store.expiry_rules if store else [7, 3, 1]) if int(x) >= 0), reverse=True) if store else [7, 3, 1]
    
    def get_batches_for_days(days_filter):
        if days_filter == "expired":
            return db.query(Batch).filter(Batch.expiry_date < today, Batch.quantity_available > 0).all()
        elif days_filter == "today":
            return db.query(Batch).filter(Batch.expiry_date == today, Batch.quantity_available > 0).all()
        else:
            days = int(days_filter)
            threshold = today + timedelta(days=days)
            return db.query(Batch).filter(Batch.expiry_date <= threshold, Batch.expiry_date >= today, Batch.quantity_available > 0).order_by(Batch.expiry_date.asc()).all()
    
    # Build categories from expiry rules
    categories = ["expired", "today"] + [str(d) for d in expiry_rules if d > 0]
    # Add 14 and 30 as optional extended views
    if 14 not in expiry_rules:
        categories.append("14")
    if 30 not in expiry_rules:
        categories.append("30")
    
    result = {}
    
    for cat in categories:
        batches = get_batches_for_days(cat)
        items = []
        total_value = 0
        for b in batches:
            prod = db.query(Product).filter(Product.id == b.product_id).first()
            if not prod:
                continue
            val = float((b.purchase_price or prod.purchase_price) * b.quantity_available)
            total_value += val
            items.append({
                "batch_id": b.id,
                "product_id": b.product_id,
                "product_name": prod.name,
                "sku": prod.sku,
                "ean": prod.ean,
                "batch_number": b.batch_number,
                "expiry_date": b.expiry_date.isoformat() if b.expiry_date else None,
                "days_until": (b.expiry_date - today).days if b.expiry_date else None,
                "quantity": b.quantity_available,
                "location_id": b.warehouse_location_id,
                "value": val,
                "selling_price": float(prod.selling_price)
            })
        result[cat] = {"count": len(items), "total_value": total_value, "items": items}
    
    return result
