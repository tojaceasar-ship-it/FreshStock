from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_permission
from app.models.product import Product
from app.models.sale import Sale, SaleItem
from app.models.waste import Waste
from app.models.user import User
from app.models.onboarding import StoreSettings
from app.services.smart_markdown import build_markdown_suggestions

from app.services.plans import require_feature
router = APIRouter(dependencies=[Depends(require_feature("savings_dashboard"))])


@router.get("")
def savings_dashboard(
    days: int = Query(30, ge=1, le=366),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("reports:read")),
):
    end = datetime.combine(date.today() + timedelta(days=1), datetime.min.time())
    start = end - timedelta(days=days)
    previous_start = start - timedelta(days=days)
    rows = db.query(SaleItem, Sale, Product).join(Sale, Sale.id == SaleItem.sale_id).join(
        Product, Product.id == SaleItem.product_id
    ).filter(
        Sale.tenant_id == current_user.tenant_id,
        Sale.sale_date >= start,
        Sale.sale_date < end,
        SaleItem.promotion_id.isnot(None),
        SaleItem.recovered_revenue > 0,
    ).all()

    recovered_revenue = sum(float(item.recovered_revenue or 0) for item, _, _ in rows)
    protected_cost = sum(float(item.protected_cost or 0) for item, _, _ in rows)
    discount_given = sum(float(item.markdown_discount_value or 0) for item, _, _ in rows)
    protected_margin = max(0.0, recovered_revenue - protected_cost)
    units_rescued = sum((item.quantity for item, _, _ in rows), Decimal("0"))
    by_day: dict[str, dict] = defaultdict(lambda: {"recovered_revenue": 0.0, "protected_cost": 0.0, "units": 0})
    by_product: dict[int, dict] = {}
    for item, sale, product in rows:
        key = sale.sale_date.date().isoformat()
        by_day[key]["date"] = key
        by_day[key]["recovered_revenue"] += float(item.recovered_revenue or 0)
        by_day[key]["protected_cost"] += float(item.protected_cost or 0)
        by_day[key]["units"] += item.quantity
        product_row = by_product.setdefault(product.id, {"product_id": product.id, "product_name": product.name, "recovered_revenue": 0.0, "protected_cost": 0.0, "units": 0})
        product_row["recovered_revenue"] += float(item.recovered_revenue or 0)
        product_row["protected_cost"] += float(item.protected_cost or 0)
        product_row["units"] += item.quantity

    current_waste = sum(float(row.purchase_value or 0) for row in db.query(Waste).filter(
        Waste.tenant_id == current_user.tenant_id, Waste.created_at >= start, Waste.created_at < end,
    ).all())
    previous_waste = sum(float(row.purchase_value or 0) for row in db.query(Waste).filter(
        Waste.tenant_id == current_user.tenant_id, Waste.created_at >= previous_start, Waste.created_at < start,
    ).all())
    waste_reduction = max(0.0, previous_waste - current_waste)
    opportunities = build_markdown_suggestions(db, current_user.tenant_id)
    store = db.query(StoreSettings).filter(StoreSettings.tenant_id == current_user.tenant_id).first()

    return {
        "currency": store.currency if store else "PLN",
        "period": {"days": days, "from": start.date().isoformat(), "to": (end - timedelta(days=1)).date().isoformat()},
        "summary": {
            "verified_savings": round(protected_cost, 2),
            "recovered_revenue": round(recovered_revenue, 2),
            "protected_margin": round(protected_margin, 2),
            "discount_given": round(discount_given, 2),
            "units_rescued": units_rescued,
            "markdown_sales": len(rows),
            "current_waste": round(current_waste, 2),
            "previous_waste": round(previous_waste, 2),
            "waste_reduction_vs_previous": round(waste_reduction, 2),
        },
        "opportunities": {
            "count": len(opportunities),
            "at_risk_cost": round(sum(item["expected_waste_cost"] for item in opportunities), 2),
            "potential_recovered_revenue": round(sum(item["potential_recovered_revenue"] for item in opportunities), 2),
        },
        "by_day": sorted(by_day.values(), key=lambda item: item["date"]),
        "by_product": sorted(by_product.values(), key=lambda item: item["protected_cost"], reverse=True)[:20],
        "methodology": {
            "verified_savings": "Część kosztu zakupu pokryta rzeczywistym przychodem ze sprzedaży partii objętych aktywną przeceną.",
            "recovered_revenue": "Rzeczywisty przychód ze sprzedaży partii objętych aktywną przeceną Smart Markdown.",
            "waste_reduction": "Porównanie strat z poprzednim okresem; wartość informacyjna, niewliczana do zweryfikowanych oszczędności.",
            "tracking_started": "Metryki sprzedaży z przeceną są naliczane od wdrożenia wersji 008.",
        },
    }
