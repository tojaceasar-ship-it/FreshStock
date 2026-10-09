from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401 - register every mapped table
from app.core.database import Base
from app.core.database import select_database_url
from app.core.idempotency import _fingerprint
from app.core.quantities import QuantityValidationError, quantity_for_unit
from app.models.batch import Batch
from app.models.product import Product, ProductUnit
from app.models.sale import SaleItem
from app.models.stock import Stock
from app.models.waste import Waste, WasteReason
from app.services.sales_engine import SalesEngineItem, process_sale


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    session.info["tenant_id"] = 1
    yield session
    session.close()


def test_unit_aware_quantity_validation():
    assert quantity_for_unit("2.75", "kg") == Decimal("2.750")
    assert quantity_for_unit("0.35", "l") == Decimal("0.350")
    assert quantity_for_unit("2", "szt") == Decimal("2.000")
    with pytest.raises(QuantityValidationError):
        quantity_for_unit("2.75", "szt")
    with pytest.raises(QuantityValidationError):
        quantity_for_unit("0", "kg")


def test_explicit_sqlite_database_is_not_replaced_by_default_file():
    audit_url = "sqlite:///./audit-20261009-data.db"
    assert select_database_url(audit_url, use_sqlite=True) == audit_url
    assert select_database_url("postgresql://localhost/freshstock", use_sqlite=True) == "sqlite:///./freshstock.db"


def test_query_driven_mutations_have_distinct_fingerprints():
    sent = _fingerprint("PUT", "/api/purchase-orders/1/status?status=sent", b"")
    confirmed = _fingerprint("PUT", "/api/purchase-orders/1/status?status=confirmed", b"")
    assert sent != confirmed


def test_weighted_fefo_sale_and_waste_preserve_precision(db):
    product = Product(
        tenant_id=1, sku="DEC-KG", name="Produkt ważony", unit=ProductUnit.KG,
        purchase_price=Decimal("4.00"), selling_price=Decimal("8.00"),
    )
    db.add(product)
    db.flush()
    batch = Batch(
        tenant_id=1, product_id=product.id, batch_number="DEC-001",
        quantity_received=Decimal("2.750"), quantity_available=Decimal("2.750"),
        purchase_price=Decimal("4.00"),
    )
    db.add(batch)
    db.flush()

    sale, _ = process_sale(
        db, sale_number="SALE-DECIMAL", source="manual", user_id=None,
        items=[SalesEngineItem(product_id=product.id, quantity=Decimal("0.350"))],
    )
    db.flush()
    assert sale.total_amount == Decimal("2.800")
    assert db.query(SaleItem).one().quantity == Decimal("0.350")

    waste_quantity = quantity_for_unit("0.10", product.unit)
    batch.quantity_available -= waste_quantity
    db.add(Waste(
        tenant_id=1, product_id=product.id, batch_id=batch.id,
        quantity=waste_quantity, purchase_value=Decimal("0.40"),
        sale_value=Decimal("0.80"), reason=WasteReason.DAMAGED,
    ))
    db.commit()

    assert batch.quantity_available == Decimal("2.300")
    assert db.query(SaleItem).one().quantity == Decimal("0.350")
    assert db.query(Waste).one().quantity == Decimal("0.100")
