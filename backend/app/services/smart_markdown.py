from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.batch import Batch
from app.models.onboarding import StoreSettings
from app.models.product import Product
from app.models.promotion import Promotion, PromotionStatus
from app.models.sale import Sale, SaleItem


MONEY = Decimal("0.01")


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY, rounding=ROUND_HALF_UP)


def build_markdown_suggestions(db: Session, tenant_id: int, *, today: date | None = None) -> list[dict]:
    """Return explainable, margin-safe markdown recommendations for expiring batches."""
    today = today or date.today()
    store = db.query(StoreSettings).filter(StoreSettings.tenant_id == tenant_id).first()
    if store and not store.markdown_suggestions_enabled:
        return []

    rules = sorted((store.markdown_rules if store else []) or [
        {"days": 7, "discount": 10},
        {"days": 3, "discount": 25},
        {"days": 1, "discount": 50},
    ], key=lambda rule: int(rule.get("days", 0)))
    max_days = max((int(rule.get("days", 0)) for rule in rules), default=0)
    sales_since = datetime.combine(today - timedelta(days=28), datetime.min.time())

    sales_rows = (
        db.query(SaleItem.product_id, func.coalesce(func.sum(SaleItem.quantity), 0))
        .join(Sale, Sale.id == SaleItem.sale_id)
        .filter(Sale.tenant_id == tenant_id, Sale.sale_date >= sales_since)
        .group_by(SaleItem.product_id)
        .all()
    )
    sold_28d = {product_id: Decimal(quantity) for product_id, quantity in sales_rows}
    products = {
        product.id: product
        for product in db.query(Product).filter(Product.tenant_id == tenant_id, Product.is_active.is_(True)).all()
    }
    batches = db.query(Batch).filter(
        Batch.tenant_id == tenant_id,
        Batch.quantity_available > 0,
        Batch.expiry_date.isnot(None),
        Batch.expiry_date >= today,
        Batch.expiry_date <= today + timedelta(days=max_days),
    ).all()
    active_batch_ids = {
        row[0]
        for row in db.query(Promotion.batch_id).filter(
            Promotion.tenant_id == tenant_id,
            Promotion.batch_id.isnot(None),
            Promotion.status.in_([PromotionStatus.SUGGESTED, PromotionStatus.APPROVED, PromotionStatus.ACTIVE]),
        ).all()
    }

    suggestions: list[dict] = []
    for batch in batches:
        if batch.id in active_batch_ids:
            continue
        product = products.get(batch.product_id)
        if not product or Decimal(product.selling_price or 0) <= 0:
            continue
        days_until = (batch.expiry_date - today).days
        matching = [rule for rule in rules if days_until <= int(rule.get("days", 0))]
        if not matching:
            continue

        base_discount = int(min(matching, key=lambda rule: int(rule.get("days", 0))).get("discount", 0))
        sold = sold_28d.get(product.id, 0)
        avg_daily = Decimal(sold) / Decimal(28)
        sellable_days = max(days_until + 1, 1)
        projected_sales = avg_daily * Decimal(sellable_days)
        at_risk_quantity = max(Decimal("0"), Decimal(batch.quantity_available) - projected_sales)
        risk_ratio = Decimal(at_risk_quantity) / Decimal(batch.quantity_available)

        demand_boost = 15 if risk_ratio >= Decimal("0.75") else 10 if risk_ratio >= Decimal("0.50") else 5 if risk_ratio >= Decimal("0.25") else 0
        urgency_boost = 10 if days_until <= 1 else 5 if days_until <= 3 else 0
        requested_discount = min(60, base_discount + demand_boost + urgency_boost)

        regular_price = Decimal(product.selling_price)
        purchase_price = Decimal(batch.purchase_price if batch.purchase_price is not None else product.purchase_price or 0)
        raw_price = regular_price * (Decimal(100 - requested_discount) / Decimal(100))
        suggested_price = _money(max(raw_price, purchase_price))
        discount_percent = int(((regular_price - suggested_price) / regular_price * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        if discount_percent <= 0:
            continue

        confidence = "HIGH" if sold >= 14 else "MEDIUM" if sold > 0 else "LOW"
        margin_floor_applied = suggested_price == _money(purchase_price) and raw_price < purchase_price
        reason_parts = [f"{days_until} dni do terminu", f"prognoza sprzedaży {float(projected_sales):.1f} szt.", f"zagrożone {at_risk_quantity} z {batch.quantity_available} szt."]
        if margin_floor_applied:
            reason_parts.append("cena ograniczona do kosztu zakupu")

        suggestions.append({
            "product_id": product.id,
            "product_name": product.name,
            "sku": product.sku,
            "ean": product.ean,
            "batch_id": batch.id,
            "batch_number": batch.batch_number,
            "expiry_date": batch.expiry_date.isoformat(),
            "days_until_expiry": days_until,
            "quantity": batch.quantity_available,
            "at_risk_quantity": at_risk_quantity,
            "avg_daily_sales": round(float(avg_daily), 2),
            "projected_sales_before_expiry": round(float(projected_sales), 2),
            "sell_through_risk_percent": int((risk_ratio * 100).quantize(Decimal("1"))),
            "original_price": float(regular_price),
            "suggested_price": float(suggested_price),
            "discount_percent": discount_percent,
            "base_discount_percent": base_discount,
            "purchase_price": float(purchase_price),
            "margin_floor_applied": margin_floor_applied,
            "confidence": confidence,
            "explanation": "; ".join(reason_parts),
            "potential_recovered_revenue": float(_money(suggested_price * at_risk_quantity)),
            "expected_waste_cost": float(_money(purchase_price * at_risk_quantity)),
            # Kept for compatibility with the existing UI.
            "recovered_value": float(_money(suggested_price * at_risk_quantity)),
            "total_value_at_cost": float(_money(purchase_price * batch.quantity_available)),
            "risk_score": int(min(100, risk_ratio * 70 + Decimal(max(0, 7 - days_until)) * Decimal("4.3"))),
        })

    return sorted(suggestions, key=lambda item: (-item["risk_score"], item["days_until_expiry"], -item["expected_waste_cost"]))
