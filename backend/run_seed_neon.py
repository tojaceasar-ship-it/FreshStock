"""
Runs the seed script against Neon using pg8000 driver.
"""
import os
import sys
import re

neon_url = os.environ.get("DATABASE_URL")
if not neon_url:
    print("ERR DATABASE_URL environment variable is required but not set")
    print("Set DATABASE_URL to your Neon connection string")
    sys.exit(1)

pg8k_url = re.sub(r"channel_binding=[^&]+&?", "", neon_url)
pg8k_url = pg8k_url.rstrip("?&")
pg8k_url = pg8k_url.replace("postgresql://", "postgresql+pg8000://")
pg8k_url = re.sub(r"[?&]?sslmode=require", "", pg8k_url)
pg8k_url = pg8k_url.rstrip("?&")

print(f"Connecting to Neon...")

os.environ["DATABASE_URL"] = pg8k_url

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

engine = create_engine(
    pg8k_url,
    connect_args={"ssl_context": True},
    pool_pre_ping=True
)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")

import app.core.database as db_module
db_module.engine = engine
db_module.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Now import and run seed
from app.seed import seed

print("Running seed...")
seed()
print("Seed completed!")
