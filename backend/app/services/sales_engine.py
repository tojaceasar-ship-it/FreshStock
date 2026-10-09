from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from app.models.alert import Alert, AlertSeverity, AlertType
from app.models.batch import Batch
from app.models.product import Product
from app.models.sale import Sale, SaleItem, SaleSource
from app.models.promotion import Promotion, PromotionStatus
from app.models.stock import Stock
from app.models.stock_movement import MovementType, StockMovement
from app.core.quantities import QuantityValidationError, quantity_for_unit


class SalesEngineError(Exception):
    pass


class InsufficientStockError(SalesEngineError):
    def __init__(self, product_id: int, requested: Decimal, available: Decimal):
        self.product_id = product_id
        self.requested = requested
        self.available = available
        super().__init__(f"Niewystarczający stan dla produktu {product_id}: dostępne {available}, żądane {requested}")


@dataclass(frozen=True)
class SalesEngineItem:
    product_id: int
    quantity: Decimal
    unit_price: Optional[Decimal] = None


def _source(value: str | SaleSource) -> SaleSource:
    if isinstance(value, SaleSource):
        return value
    try:
        return SaleSource(value)
    except ValueError:
        return SaleSource.API


def _promotion_for_batch(db: Session, *, product: Product, batch: Batch, at: datetime) -> Optional[Promotion]:
    return db.query(Promotion).filter(
        Promotion.tenant_id == product.tenant_id,
        Promotion.product_id == product.id,
        (Promotion.batch_id == batch.id) | (Promotion.batch_id.is_(None)),
        Promotion.status == PromotionStatus.ACTIVE,
        (Promotion.start_date.is_(None)) | (Promotion.start_date <= at),
        (Promotion.end_date.is_(None)) | (Promotion.end_date >= at),
    ).order_by(Promotion.batch_id.desc().nullslast(), Promotion.created_at.desc()).first()


def process_sale(
    db: Session,
    *,
    sale_number: str,
    items: Iterable[SalesEngineItem],
    user_id: Optional[int],
    source: str | SaleSource,
    sale_date: Optional[datetime] = None,
    allow_partial_stock: bool = False,
    reference_type: str = "sale",
    fefo_enabled: bool = True,
) -> tuple[Sale, list[dict]]:
    """Single transaction script used by manual, CSV and POS sales.

    The caller owns commit/rollback. Batches are locked on PostgreSQL to avoid
    concurrent double allocation.
    """
    normalized_items = list(items)
    if not normalized_items:
        raise SalesEngineError("Sprzedaż nie zawiera pozycji")
    if any(item.quantity <= 0 for item in normalized_items):
        # Validate the complete request before inserting/flushing the Sale row.
        # This keeps malformed requests atomic and prevents unrelated unique
        # constraint errors from masking the actual validation failure.
        raise SalesEngineError("Ilość sprzedaży musi być dodatnia")

    effective_sale_date = sale_date or datetime.now(timezone.utc)
    tenant_id = int(db.info.get("tenant_id", 1))
    sale = Sale(
        tenant_id=tenant_id,
        sale_number=sale_number,
        sale_date=effective_sale_date,
        total_amount=Decimal("0"),
        source=_source(source),
        created_by=user_id,
    )
    db.add(sale)
    db.flush()

    total_amount = Decimal("0")
    shortages: list[dict] = []
    cache = db.info.setdefault("sales_engine_cache", {"products": {}, "batches": {}, "stock": {}})
    for requested in normalized_items:
        product = cache["products"].get(requested.product_id)
        if product is None:
            product = db.query(Product).filter(Product.id == requested.product_id, Product.tenant_id == tenant_id).first()
            if product:
                cache["products"][requested.product_id] = product
        if not product:
            raise SalesEngineError(f"Produkt {requested.product_id} nie istnieje")
        try:
            requested_quantity = quantity_for_unit(requested.quantity, product.unit)
        except QuantityValidationError as exc:
            raise SalesEngineError(str(exc)) from exc
        regular_price = Decimal(product.selling_price)

        batch_key = (requested.product_id, fefo_enabled)
        batches = cache["batches"].get(batch_key)
        if batches is None:
            from app.services.fefo import sellable_batch_filter
            batches = db.query(Batch).filter(
                Batch.tenant_id == tenant_id,
                Batch.product_id == requested.product_id,
                Batch.quantity_available > 0,
                sellable_batch_filter(),
            ).order_by(Batch.expiry_date.asc().nulls_last() if fefo_enabled else Batch.created_at.asc(), Batch.created_at.asc()).with_for_update().all()
            cache["batches"][batch_key] = batches
        available = sum(batch.quantity_available for batch in batches)
        if available < requested_quantity and not allow_partial_stock:
            raise InsufficientStockError(requested.product_id, requested_quantity, available)

        remaining = requested_quantity
        for batch in batches:
            if remaining <= 0:
                break
            take = min(remaining, batch.quantity_available)
            if take <= 0:
                continue
            batch.quantity_available -= take
            if batch.warehouse_location_id:
                stock_key = (requested.product_id, batch.warehouse_location_id)
                stock = cache["stock"].get(stock_key)
                if stock is None:
                    stock = db.query(Stock).filter(
                        Stock.tenant_id == tenant_id,
                        Stock.product_id == requested.product_id,
                        Stock.location_id == batch.warehouse_location_id,
                    ).with_for_update().first()
                    if stock:
                        cache["stock"][stock_key] = stock
                if stock:
                    stock.quantity = max(0, stock.quantity - take)
            promotion = _promotion_for_batch(db, product=product, batch=batch, at=effective_sale_date)
            unit_price = Decimal(requested.unit_price) if requested.unit_price is not None else Decimal(promotion.discounted_price if promotion else regular_price)
            qualifies_for_savings = bool(promotion and unit_price < regular_price and unit_price <= Decimal(promotion.discounted_price) * Decimal("1.02"))
            line_total = Decimal(take) * unit_price
            purchase_price = Decimal(batch.purchase_price if batch.purchase_price is not None else product.purchase_price or 0)
            discount_value = max(Decimal("0"), (regular_price - unit_price) * take) if qualifies_for_savings else Decimal("0")
            recovered_revenue = line_total if qualifies_for_savings else Decimal("0")
            protected_cost = min(line_total, purchase_price * take) if qualifies_for_savings else Decimal("0")
            total_amount += line_total
            db.add(SaleItem(
                tenant_id=product.tenant_id,
                sale_id=sale.id, product_id=requested.product_id, batch_id=batch.id,
                promotion_id=promotion.id if qualifies_for_savings else None,
                quantity=take, unit_price=unit_price, regular_unit_price=regular_price, total_price=line_total,
                markdown_discount_value=discount_value, recovered_revenue=recovered_revenue, protected_cost=protected_cost,
            ))
            db.add(StockMovement(
                tenant_id=tenant_id,
                product_id=requested.product_id, batch_id=batch.id, quantity=-take,
                movement_type=MovementType.SALE, source_location_id=batch.warehouse_location_id,
                user_id=user_id, reason=f"Sprzedaż {sale.sale_number}", reference_id=str(sale.id), reference_type=reference_type,
            ))
            remaining -= take

        if remaining > 0:
            # The unallocated line preserves the POS truth while never creating
            # a negative batch. Reconciliation can resolve the shortage later.
            unit_price = Decimal(requested.unit_price) if requested.unit_price is not None else regular_price
            line_total = Decimal(remaining) * unit_price
            total_amount += line_total
            db.add(SaleItem(
                tenant_id=product.tenant_id,
                sale_id=sale.id, product_id=requested.product_id, batch_id=None,
                quantity=remaining, unit_price=unit_price, regular_unit_price=regular_price, total_price=line_total,
                markdown_discount_value=0, recovered_revenue=0, protected_cost=0,
            ))
            shortage = {
                "product_id": requested.product_id,
                "expected_quantity": requested_quantity,
                "available_quantity": available,
                "difference": remaining,
            }
            shortages.append(shortage)
            db.add(Alert(
                tenant_id=tenant_id,
                alert_type=AlertType.INVENTORY_DESYNC,
                severity=AlertSeverity.HIGH,
                title="Rozbieżność stanu po sprzedaży POS",
                message=f"POS sprzedał {requested_quantity}, dostępne partie: {available}, brak: {remaining}. Sprzedaż {sale.sale_number}",
                product_id=requested.product_id,
            ))

    sale.total_amount = total_amount
    db.flush()
    return sale, shortages


def reverse_sale(db: Session, *, sale: Sale, user_id: Optional[int]) -> Decimal:
    existing = db.query(StockMovement).filter(
        StockMovement.reference_type == "sale_reversal",
        StockMovement.reference_id == str(sale.id),
    ).first()
    if existing:
        return Decimal("0")
    reversed_quantity = Decimal("0")
    for item in sale.items:
        if not item.batch_id:
            continue
        batch = db.query(Batch).filter(Batch.id == item.batch_id).with_for_update().first()
        if not batch:
            raise SalesEngineError(f"Partia {item.batch_id} z oryginalnej sprzedaży nie istnieje")
        batch.quantity_available += item.quantity
        if batch.warehouse_location_id:
            stock = db.query(Stock).filter(Stock.product_id == item.product_id, Stock.location_id == batch.warehouse_location_id).with_for_update().first()
            if stock:
                stock.quantity += item.quantity
        db.add(StockMovement(
            product_id=item.product_id, batch_id=batch.id, quantity=item.quantity,
            movement_type=MovementType.SALE_REVERSAL, destination_location_id=batch.warehouse_location_id,
            user_id=user_id, reason=f"Anulowanie sprzedaży {sale.sale_number}",
            reference_id=str(sale.id), reference_type="sale_reversal",
        ))
        reversed_quantity += item.quantity
    return reversed_quantity
