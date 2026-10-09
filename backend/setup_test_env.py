"""Test environment setup: creates FRESHSTOCK_E2E_TEST tenant with QA STORE and controlled data."""
import os
import sys
import random
from datetime import date, datetime, timedelta
from decimal import Decimal

os.environ["USE_SQLITE"] = "true"
os.environ["DATABASE_URL"] = "sqlite:///./freshstock.db"

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import func, text
from app.core.database import Base, engine, SessionLocal
from app.models import *  # noqa
from app.core.security import get_password_hash
from app.models.tenant import Tenant
from app.models.user import User, UserRole
from app.models.onboarding import StoreSettings, OnboardingProgress
from app.models.category import Category
from app.models.supplier import Supplier
from app.models.product import Product, ProductUnit, ProductSupplier
from app.models.location import WarehouseLocation, LocationType
from app.models.batch import Batch
from app.models.stock import Stock
from app.models.stock_movement import StockMovement, MovementType

TENANT_NAME = "FRESHSTOCK_E2E_TEST"
STORE_NAME = "QA STORE"
USERS = [
    ("qa.owner@freshstock.test", "qa.owner", UserRole.OWNER, "QaOwner#2026"),
    ("qa.manager@freshstock.test", "qa.manager", UserRole.MANAGER, "QaManager#2026"),
    ("qa.warehouse@freshstock.test", "qa.warehouse", UserRole.WAREHOUSE, "QaWarehouse#2026"),
    ("qa.employee@freshstock.test", "qa.employee", UserRole.EMPLOYEE, "QaEmployee#2026"),
    ("qa.viewer@freshstock.test", "qa.viewer", UserRole.VIEWER, "QaViewer#2026"),
]


def wipe(db):
    print("Wiping existing data...")
    # Derive the table list from the live schema so it can never drift from the
    # models. SQLite ignores PRAGMA foreign_keys changes made inside a
    # transaction, so commit first, disable FK enforcement, wipe, then restore.
    db.commit()
    db.execute(text("PRAGMA foreign_keys=OFF"))
    db.commit()
    tables = [
        row[0] for row in db.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
        ).fetchall()
    ]
    for table in tables:
        try:
            db.execute(text(f'DELETE FROM "{table}"'))
            db.commit()
        except Exception as exc:
            db.rollback()
            print(f"  skip {table}: {exc}")
    print(f"  wiped {len(tables)} tables")
    db.execute(text("PRAGMA foreign_keys=ON"))
    db.commit()

def main():
    print("Creating tables...")
    Base.metadata.create_all(bind=engine)
    print(f"Tables: {len(Base.metadata.tables)}")

    db = SessionLocal()
    try:
        wipe(db)

        tenant = Tenant(name=TENANT_NAME)
        db.add(tenant)
        db.flush()
        tid = tenant.id
        print(f"Tenant {TENANT_NAME} id={tid}")

        db.add(StoreSettings(
            tenant_id=tid, store_name=STORE_NAME, language="pl", country="PL",
            currency="PLN", timezone="Europe/Warsaw",
            expiry_rules=[], markdown_rules=[], dashboard_layout=[],
        ))
        db.add(OnboardingProgress(
            tenant_id=tid, current_step=1, completed_steps=[],
            step_data={}, status="NOT_STARTED",
        ))

        for email, username, role, password in USERS:
            db.add(User(
                tenant_id=tid, email=email, username=username,
                hashed_password=get_password_hash(password),
                full_name=username.split(".")[-1].title(), role=role,
                is_active=True,
            ))
        db.commit()
        print(f"Users: {db.query(User).filter(User.tenant_id == tid).count()}")

        cats = []
        for name, color in [("Nabiał QA", "#3B82F6"), ("Pieczywo QA", "#F59E0B"),
                            ("Napoje QA", "#10B981"), ("Chemia QA", "#8B5CF6")]:
            c = Category(tenant_id=tid, name=name, description=f"{name} kategoria", color=color)
            db.add(c); cats.append(c)
        db.commit()
        for c in cats:
            db.refresh(c)
        print(f"Categories: {len(cats)}")

        sups = []
        for i in range(10):
            s = Supplier(
                tenant_id=tid, name=f"QA Supplier {i+1}",
                email=f"supplier{i+1}@qa.test", phone=f"50000000{i:02d}",
                vat_number=f"PLQA{i:010d}", contact_person=f"Kontakt QA {i+1}",
                payment_terms="14 dni", min_order_value=Decimal("100"),
                lead_time_days=1 + (i % 3), is_active=True, notes="QA",
            )
            db.add(s); sups.append(s)
        db.commit()
        for s in sups:
            db.refresh(s)
        print(f"Suppliers: {len(sups)}")

        locs = []
        loc_defs = [
            ("QA Sklep", "QA-STORE", LocationType.STORE, None),
            ("QA Magazyn", "QA-WH", LocationType.WAREHOUSE, None),
            ("QA Chłodnia", "QA-FRIDGE", LocationType.FRIDGE, None),
            ("QA Regał A1", "QA-SHELF-A1", LocationType.SHELF, None),
            ("QA Regał A2", "QA-SHELF-A2", LocationType.SHELF, None),
        ]
        for name, code, typ, parent in loc_defs:
            loc = WarehouseLocation(tenant_id=tid, name=name, code=code, type=typ, parent_id=parent)
            db.add(loc); locs.append(loc)
        db.commit()
        for loc in locs:
            db.refresh(loc)
        wh = next(l for l in locs if l.code == "QA-WH")
        for loc in locs:
            if loc.code.startswith("QA-SHELF"):
                loc.parent_id = wh.id
        db.commit()
        print(f"Locations: {len(locs)}")

        # 100 products
        products = []
        for i in range(100):
            n = i + 1
            requires_exp = (i % 3) != 0
            cat = cats[i % len(cats)]
            sup = sups[i % len(sups)]
            pur = round(2.0 + (i % 20) * 0.75, 2)
            p = Product(
                tenant_id=tid,
                sku=f"QA-{n:04d}",
                ean=f"59099999{n:06d}",
                name=f"QA Produkt {n}",
                brand="QA Brand",
                category_id=cat.id,
                unit=ProductUnit.PCS,
                vat_rate=Decimal("23.00"),
                purchase_price=Decimal(str(pur)),
                selling_price=Decimal(str(round(pur * 1.6, 2))),
                min_stock=10, target_stock=30, safety_stock=5,
                is_active=True, default_supplier_id=sup.id,
                requires_expiry_control=requires_exp,
                expiry_warning_days=7 if requires_exp else 0,
            )
            db.add(p); products.append(p)
        db.commit()
        for p in products:
            db.refresh(p)
        print(f"Products: {len(products)}")

        for p in products:
            db.add(ProductSupplier(
                tenant_id=tid, product_id=p.id, supplier_id=p.default_supplier_id,
                purchase_price=p.purchase_price, is_preferred=True,
            ))
        db.commit()

        # QA MILK for FEFO E2E
        qa_milk = Product(
            tenant_id=tid, sku="QA-MILK", ean="8712345678901",
            name="QA MILK", brand="QA", category_id=cats[0].id,
            unit=ProductUnit.PCS, vat_rate=Decimal("23.00"),
            purchase_price=Decimal("2.50"), selling_price=Decimal("3.99"),
            min_stock=5, target_stock=20, safety_stock=2, is_active=True,
            default_supplier_id=sups[0].id, requires_expiry_control=True,
            expiry_warning_days=7,
        )
        db.add(qa_milk)
        db.commit()
        db.refresh(qa_milk)
        print(f"QA MILK id={qa_milk.id} ean={qa_milk.ean}")

        # Expiry bucket products
        today = date.today()
        bucket_specs = [
            ("QA-EXPIRED", "QA Expiry Expired", -5, 12),
            ("QA-EXP-TODAY", "QA Expiry Today", 0, 9),
            ("QA-EXP-1D", "QA Expiry 1 Day", 1, 11),
            ("QA-EXP-3D", "QA Expiry 3 Days", 3, 14),
            ("QA-EXP-7D", "QA Expiry 7 Days", 7, 8),
            ("QA-EXP-14D", "QA Expiry 14 Days", 14, 16),
            ("QA-EXP-30D", "QA Expiry 30 Days", 30, 20),
        ]
        bucket_products = {}
        for sku, name, offset, qty in bucket_specs:
            p = Product(
                tenant_id=tid, sku=sku, ean=f"5910000{abs(hash(sku)) % 1000000:06d}",
                name=name, brand="QA", category_id=cats[0].id, unit=ProductUnit.PCS,
                vat_rate=Decimal("23.00"), purchase_price=Decimal("5.00"),
                selling_price=Decimal("8.00"), min_stock=5, target_stock=20,
                safety_stock=2, is_active=True, default_supplier_id=sups[0].id,
                requires_expiry_control=True, expiry_warning_days=30,
            )
            db.add(p)
            db.flush()
            db.add(Batch(
                tenant_id=tid, product_id=p.id,
                batch_number=f"{sku}-B1",
                expiry_date=today + timedelta(days=offset),
                manufacture_date=today - timedelta(days=10),
                quantity_received=qty, quantity_available=qty,
                purchase_price=p.purchase_price, supplier_id=sups[0].id,
                warehouse_location_id=locs[1].id,
            ))
            db.add(Stock(tenant_id=tid, product_id=p.id, location_id=locs[1].id, quantity=qty))
            bucket_products[sku] = p

        # No-expiry product
        noexp = Product(
            tenant_id=tid, sku="QA-NOEXP", ean="5920000000001",
            name="QA Bez Ważności", brand="QA", category_id=cats[2].id,
            unit=ProductUnit.PCS, vat_rate=Decimal("23.00"),
            purchase_price=Decimal("1.00"), selling_price=Decimal("2.00"),
            min_stock=5, target_stock=20, safety_stock=2, is_active=True,
            default_supplier_id=sups[2].id, requires_expiry_control=False,
            expiry_warning_days=0,
        )
        db.add(noexp); db.flush()
        db.add(Batch(
            tenant_id=tid, product_id=noexp.id, batch_number="QA-NOEXP-B1",
            expiry_date=None, manufacture_date=None,
            quantity_received=25, quantity_available=25,
            purchase_price=noexp.purchase_price, supplier_id=sups[2].id,
            warehouse_location_id=locs[1].id,
        ))
        db.add(Stock(tenant_id=tid, product_id=noexp.id, location_id=locs[1].id, quantity=25))

        # Multi-batch product (FEFO controlled)
        multi = Product(
            tenant_id=tid, sku="QA-MULTI", ean="5930000000001",
            name="QA Multi Batch", brand="QA", category_id=cats[1].id,
            unit=ProductUnit.PCS, vat_rate=Decimal("23.00"),
            purchase_price=Decimal("4.00"), selling_price=Decimal("6.50"),
            min_stock=5, target_stock=30, safety_stock=2, is_active=True,
            default_supplier_id=sups[1].id, requires_expiry_control=True,
            expiry_warning_days=7,
        )
        db.add(multi); db.flush()
        # Batch A earlier expiry, Batch B later
        db.add(Batch(tenant_id=tid, product_id=multi.id, batch_number="QA-MULTI-A",
                     expiry_date=today + timedelta(days=2), manufacture_date=today - timedelta(days=8),
                     quantity_received=3, quantity_available=3,
                     purchase_price=multi.purchase_price, supplier_id=sups[1].id,
                     warehouse_location_id=locs[1].id))
        db.add(Batch(tenant_id=tid, product_id=multi.id, batch_number="QA-MULTI-B",
                     expiry_date=today + timedelta(days=20), manufacture_date=today - timedelta(days=1),
                     quantity_received=10, quantity_available=10,
                     purchase_price=multi.purchase_price, supplier_id=sups[1].id,
                     warehouse_location_id=locs[1].id))
        db.add(Stock(tenant_id=tid, product_id=multi.id, location_id=locs[1].id, quantity=13))

        # QA MILK batches: A=3 earlier, B=10 later
        db.add(Batch(tenant_id=tid, product_id=qa_milk.id, batch_number="QA-MILK-A",
                     expiry_date=today + timedelta(days=1), manufacture_date=today - timedelta(days=6),
                     quantity_received=3, quantity_available=3,
                     purchase_price=qa_milk.purchase_price, supplier_id=sups[0].id,
                     warehouse_location_id=locs[1].id))
        db.add(Batch(tenant_id=tid, product_id=qa_milk.id, batch_number="QA-MILK-B",
                     expiry_date=today + timedelta(days=7), manufacture_date=today,
                     quantity_received=10, quantity_available=10,
                     purchase_price=qa_milk.purchase_price, supplier_id=sups[0].id,
                     warehouse_location_id=locs[1].id))
        db.add(Stock(tenant_id=tid, product_id=qa_milk.id, location_id=locs[1].id, quantity=13))

        # Low stock / zero stock / overstock
        db.add(Product(tenant_id=tid, sku="QA-LOWSTOCK", ean="5940000000001",
                       name="QA Low Stock", brand="QA", category_id=cats[1].id,
                       unit=ProductUnit.PCS, vat_rate=Decimal("23.00"),
                       purchase_price=Decimal("3.00"), selling_price=Decimal("5.00"),
                       min_stock=20, target_stock=50, safety_stock=10, is_active=True,
                       default_supplier_id=sups[1].id, requires_expiry_control=True,
                       expiry_warning_days=7))
        db.add(Product(tenant_id=tid, sku="QA-ZEROSTOCK", ean="5950000000001",
                       name="QA Zero Stock", brand="QA", category_id=cats[1].id,
                       unit=ProductUnit.PCS, vat_rate=Decimal("23.00"),
                       purchase_price=Decimal("3.00"), selling_price=Decimal("5.00"),
                       min_stock=10, target_stock=30, safety_stock=5, is_active=True,
                       default_supplier_id=sups[1].id, requires_expiry_control=True,
                       expiry_warning_days=7))
        db.add(Product(tenant_id=tid, sku="QA-OVERSTOCK", ean="5960000000001",
                       name="QA Overstock", brand="QA", category_id=cats[1].id,
                       unit=ProductUnit.PCS, vat_rate=Decimal("23.00"),
                       purchase_price=Decimal("3.00"), selling_price=Decimal("5.00"),
                       min_stock=5, target_stock=10, safety_stock=2, is_active=True,
                       default_supplier_id=sups[1].id, requires_expiry_control=True,
                       expiry_warning_days=7))
        db.commit()

        low = db.query(Product).filter(Product.tenant_id == tid, Product.sku == "QA-LOWSTOCK").one()
        zero = db.query(Product).filter(Product.tenant_id == tid, Product.sku == "QA-ZEROSTOCK").one()
        over = db.query(Product).filter(Product.tenant_id == tid, Product.sku == "QA-OVERSTOCK").one()
        db.add(Batch(tenant_id=tid, product_id=low.id, batch_number="QA-LOW-B1",
                     expiry_date=today + timedelta(days=10), manufacture_date=today - timedelta(days=2),
                     quantity_received=5, quantity_available=5,
                     purchase_price=low.purchase_price, supplier_id=sups[1].id,
                     warehouse_location_id=locs[1].id))
        db.add(Stock(tenant_id=tid, product_id=low.id, location_id=locs[1].id, quantity=5))
        db.add(Batch(tenant_id=tid, product_id=over.id, batch_number="QA-OVER-B1",
                     expiry_date=today + timedelta(days=60), manufacture_date=today - timedelta(days=5),
                     quantity_received=500, quantity_available=500,
                     purchase_price=over.purchase_price, supplier_id=sups[1].id,
                     warehouse_location_id=locs[1].id))
        db.add(Stock(tenant_id=tid, product_id=over.id, location_id=locs[1].id, quantity=500))
        db.commit()

        print("=" * 60)
        print("TEST ENVIRONMENT READY")
        print(f"  Tenant:   {TENANT_NAME} (id={tid})")
        print(f"  Store:    {STORE_NAME}")
        print(f"  Users:    {len(USERS)} (owner/manager/warehouse/employee/viewer)")
        print(f"  Products: {db.query(Product).filter(Product.tenant_id == tid).count()}")
        print(f"  Suppliers:{db.query(Supplier).filter(Supplier.tenant_id == tid).count()}")
        print(f"  Locations:{db.query(WarehouseLocation).filter(WarehouseLocation.tenant_id == tid).count()}")
        print(f"  Batches:  {db.query(Batch).filter(Batch.tenant_id == tid).count()}")
        print("=" * 60)
        for email, username, role, password in USERS:
            print(f"  {role.value:10s} {username:14s} {password}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
