"""Deterministic, isolated audit dataset for AUDIT-2026-10-09.

Safety: the target URL must be SQLite and contain ``audit-20261009``. The
script never opens the normal freshstock.db and never deletes existing data.
Re-running a complete seed verifies counts and exits successfully.
"""
from __future__ import annotations

import os
import random
from datetime import date, timedelta
from decimal import Decimal

RUN_ID = "AUDIT-2026-10-09"
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./audit-20261009-data.db")
if not DATABASE_URL.startswith("sqlite") or "audit-20261009" not in DATABASE_URL.lower():
    raise SystemExit("Refusing unsafe target: use an isolated SQLite URL containing audit-20261009")

os.environ["USE_SQLITE"] = "true"
os.environ["DATABASE_URL"] = DATABASE_URL
os.environ.setdefault("SECRET_KEY", "audit-local-secret-key-minimum-32-characters")

import app.models  # noqa: E402,F401
import app.integrations.models  # noqa: E402,F401
from app.core.database import Base, SessionLocal, engine  # noqa: E402
from app.core.security import get_password_hash  # noqa: E402
from app.models.batch import Batch  # noqa: E402
from app.models.category import Category  # noqa: E402
from app.models.location import LocationType, WarehouseLocation  # noqa: E402
from app.models.onboarding import OnboardingProgress, StoreSettings  # noqa: E402
from app.models.product import Product, ProductUnit  # noqa: E402
from app.models.stock import Stock  # noqa: E402
from app.models.subscription import Subscription, TenantStore  # noqa: E402
from app.models.supplier import Supplier  # noqa: E402
from app.models.tenant import Tenant  # noqa: E402
from app.models.user import User, UserRole  # noqa: E402

STORES = [
    ("S01-NEW", "NOWY SKLEP", 30),
    ("S02-GROCERY", "MAŁY SKLEP SPOŻYWCZY", 120),
    ("S03-FRESH", "ŚWIEŻA ŻYWNOŚĆ", 250),
    ("S04-WEIGHT", "PRODUKTY NA WAGĘ", 180),
    ("S05-DELIVERY", "INTENSYWNE DOSTAWY", 600),
    ("S06-RETURNS", "ZWROTY I KOREKTY", 200),
    ("S07-IMPORT", "IMPORTY", 1_000),
    ("S08-TEAM", "PRACA ZESPOŁOWA", 400),
    ("S09-HARD", "TRUDNE DANE", 350),
    ("S10-PERF", "WYDAJNOŚĆ", 10_000),
]
CATEGORY_NAMES = ["Nabiał", "Pieczywo", "Warzywa", "Owoce", "Napoje", "Mrożonki", "Chemia", "Przekąski"]
PRODUCT_NAMES = ["Jogurt naturalny", "Chleb żytni", "Pomidor malinowy", "Jabłko ligol", "Sok tłoczony", "Warzywa mrożone", "Płyn ekologiczny", "Orzechy prażone"]
BRANDS = ["Dobra Farma", "Półka Lokalna", "Zielony Koszyk", "Codzienny Wybór", "Nord Market"]


def verify_existing(db) -> bool:
    tenants = db.query(Tenant).filter(Tenant.name.like(f"{RUN_ID}:%")).all()
    if not tenants:
        return False
    if len(tenants) != len(STORES):
        raise SystemExit(f"Partial audit seed exists ({len(tenants)}/10 tenants); refusing mutation")
    expected = dict((code, count) for code, _, count in STORES)
    for tenant in tenants:
        code = tenant.name.split(":", 2)[1]
        actual = db.query(Product).filter(Product.tenant_id == tenant.id).count()
        if expected.get(code) != actual:
            raise SystemExit(f"Count mismatch for {code}: expected {expected.get(code)}, got {actual}")
    print("Audit seed already complete; counts verified")
    return True


def main() -> None:
    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        if verify_existing(db):
            return
        rng = random.Random(20261009)
        password_hash = get_password_hash("Audit-only-2026!")
        today = date(2026, 10, 9)
        for store_no, (code, display_name, product_count) in enumerate(STORES, 1):
            tenant = Tenant(name=f"{RUN_ID}:{code}:{display_name}")
            db.add(tenant)
            db.flush()
            users = [
                User(tenant_id=tenant.id, email=f"{code.lower()}-{role.value.lower()}@audit.invalid",
                     username=f"audit_{store_no:02d}_{role.value.lower()}", hashed_password=password_hash,
                     full_name=f"Audit {role.value.title()} {code}", role=role, is_active=True)
                for role in UserRole
            ]
            db.add_all(users + [
                Subscription(tenant_id=tenant.id, plan="ENTERPRISE", status="ACTIVE"),
                TenantStore(tenant_id=tenant.id, name=display_name, code=code),
                StoreSettings(tenant_id=tenant.id, store_name=display_name, language="pl", country="PL",
                              currency="PLN", timezone="Europe/Warsaw", expiry_rules=[], markdown_rules=[], dashboard_layout=[]),
                OnboardingProgress(tenant_id=tenant.id, current_step=14, completed_steps=list(range(1, 15)),
                                   step_data={"run_id": RUN_ID}, status="COMPLETED"),
            ])
            categories = [Category(tenant_id=tenant.id, name=f"{name} {code}") for name in CATEGORY_NAMES]
            suppliers = [Supplier(tenant_id=tenant.id, name=f"Dostawca {i + 1} {code}", lead_time_days=1 + i) for i in range(4)]
            location = WarehouseLocation(tenant_id=tenant.id, name=f"Magazyn {code}", code="MAIN", type=LocationType.WAREHOUSE)
            db.add_all(categories + suppliers + [location])
            db.flush()
            for start in range(0, product_count, 500):
                products = []
                for index in range(start, min(start + 500, product_count)):
                    weighted = code == "S04-WEIGHT" or index % 17 == 0
                    unit = ProductUnit.KG if weighted else ProductUnit.PCS
                    purchase = Decimal(100 + (index * 37) % 5_000) / 100
                    selling = (purchase * Decimal("1.35")).quantize(Decimal("0.01"))
                    special = " Żółć 東京 🥝 <script>tekst</script>" if code == "S09-HARD" and index == 0 else ""
                    products.append(Product(
                        tenant_id=tenant.id, sku=f"{code}-{index + 1:05d}", ean=f"{store_no:02d}{index + 1:011d}",
                        name=f"{PRODUCT_NAMES[index % len(PRODUCT_NAMES)]} {index + 1}{special}",
                        brand=BRANDS[index % len(BRANDS)], category_id=categories[index % len(categories)].id,
                        unit=unit, vat_rate=Decimal("5.00") if index % 3 else Decimal("23.00"),
                        purchase_price=purchase, selling_price=selling, min_stock=Decimal("3.000"),
                        target_stock=Decimal(str(12 + index % 30)), safety_stock=Decimal("2.000"),
                        default_supplier_id=suppliers[index % len(suppliers)].id,
                        requires_expiry_control=index % 5 != 0, expiry_warning_days=3 + index % 12,
                    ))
                db.add_all(products)
                db.flush()
                batches, stocks = [], []
                for offset, product in enumerate(products, start):
                    quantity = Decimal(str(5 + offset % 96))
                    if product.unit == ProductUnit.KG:
                        quantity += Decimal(str(rng.randrange(0, 1000))) / 1000
                    expiry = today + timedelta(days=(-3 + offset % 90)) if product.requires_expiry_control else None
                    batches.append(Batch(tenant_id=tenant.id, product_id=product.id,
                                         batch_number=f"{code}-B-{offset + 1:05d}", expiry_date=expiry,
                                         quantity_received=quantity, quantity_available=quantity,
                                         purchase_price=product.purchase_price, supplier_id=product.default_supplier_id,
                                         warehouse_location_id=location.id))
                    stocks.append(Stock(tenant_id=tenant.id, product_id=product.id, location_id=location.id, quantity=quantity))
                db.add_all(batches + stocks)
                db.flush()
            db.commit()
            print(f"seeded {code}: tenant={tenant.id}, products={product_count}, users={len(users)}")
        verify_existing(db)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
