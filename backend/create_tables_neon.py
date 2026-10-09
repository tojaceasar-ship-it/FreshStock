"""
One-shot script to create all tables in Neon and run the seed.
Uses pg8000 (pure Python) instead of psycopg2 to avoid pg_config dependency.
"""
import os
import sys

# Patch DATABASE_URL to use pg8000 driver
neon_url = os.environ.get("DATABASE_URL")
if not neon_url:
    print("ERR DATABASE_URL environment variable is required but not set")
    print("Set DATABASE_URL to your Neon connection string")
    sys.exit(1)

# Convert postgresql:// -> postgresql+pg8000://
# pg8000 doesn't support channel_binding, so strip it
import re
pg8k_url = re.sub(r"channel_binding=[^&]+&?", "", neon_url)
pg8k_url = pg8k_url.rstrip("?&")
pg8k_url = pg8k_url.replace("postgresql://", "postgresql+pg8000://")
# pg8000 needs ssl=True param differently
if "sslmode=require" in pg8k_url:
    pg8k_url = pg8k_url.replace("sslmode=require", "")
    pg8k_url = pg8k_url.rstrip("?&")

print(f"Connecting with: {pg8k_url[:60]}...")

os.environ["DATABASE_URL"] = pg8k_url
os.environ["USE_SQLITE"] = "false"

# Now patch database.py to use our URL before importing anything
import sqlalchemy
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base

engine = create_engine(
    pg8k_url,
    connect_args={"ssl_context": True},
    pool_pre_ping=True
)

# Test connection
try:
    with engine.connect() as conn:
        result = conn.execute(text("SELECT version()"))
        print("OK Connected to Neon:", result.scalar()[:40])
except Exception as e:
    print(f"ERR Connection failed: {e}")
    sys.exit(1)

# Import all models (they register themselves on Base)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")

# Monkey-patch the database module before importing models
import app.core.database as db_module
db_module.engine = engine
db_module.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

from app.models import (
    Base, User, Category, Supplier, Product, ProductSupplier,
    WarehouseLocation, Batch, Stock, StockMovement,
    Delivery, DeliveryItem, PurchaseOrder, PurchaseOrderItem,
    Sale, SaleItem, Waste, Promotion, InventoryCount, InventoryCountItem,
    Alert, AuditLog, Setting
)

print("Creating all tables...")
try:
    Base.metadata.create_all(bind=engine)
    print("OK All tables created successfully!")
except Exception as e:
    print(f"ERR Table creation failed: {e}")
    sys.exit(1)

print("\nAll done! Run the seed script next if needed.")
print("Tables created:")
with engine.connect() as conn:
    result = conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"))
    for row in result:
        print(f"  - {row[0]}")
