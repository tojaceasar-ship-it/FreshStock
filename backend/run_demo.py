"""Demo runner with SQLite - creates tables and seeds"""
import os
os.environ["USE_SQLITE"] = "true"
os.environ["DATABASE_URL"] = "sqlite:///./freshstock.db"

from app.core.database import Base, engine, SessionLocal
from app.models import *  # noqa
from app.core.security import get_password_hash
from app.models.user import User, UserRole
from datetime import datetime

print("Creating tables...")
Base.metadata.create_all(bind=engine)
print(f"Tables created: {len(Base.metadata.tables)}")

# Check if users exist, if not seed minimal
db = SessionLocal()
try:
    user_count = db.query(User).count()
    print(f"Existing users: {user_count}")
    if user_count == 0:
        print("Seeding minimal users...")
        password_names = ["DEMO_OWNER_PASSWORD", "DEMO_MANAGER_PASSWORD", "DEMO_WAREHOUSE_PASSWORD", "DEMO_EMPLOYEE_PASSWORD"]
        missing = [name for name in password_names if not os.getenv(name)]
        if missing:
            raise RuntimeError(f"Ustaw silne hasła demo: {', '.join(missing)}")
        users = [
            User(email="owner@freshstock.pl", username="owner", hashed_password=get_password_hash(os.environ["DEMO_OWNER_PASSWORD"]), full_name="Jan Właściciel", role=UserRole.OWNER, is_active=True),
            User(email="manager@freshstock.pl", username="manager", hashed_password=get_password_hash(os.environ["DEMO_MANAGER_PASSWORD"]), full_name="Anna Kowalska", role=UserRole.MANAGER, is_active=True),
            User(email="warehouse@freshstock.pl", username="warehouse", hashed_password=get_password_hash(os.environ["DEMO_WAREHOUSE_PASSWORD"]), full_name="Marek Magazynier", role=UserRole.WAREHOUSE, is_active=True),
            User(email="employee@freshstock.pl", username="employee", hashed_password=get_password_hash(os.environ["DEMO_EMPLOYEE_PASSWORD"]), full_name="Ewa Pracownik", role=UserRole.EMPLOYEE, is_active=True),
        ]
        db.add_all(users)
        db.commit()
        print("Users seeded")
    
    # Now run full seed if requested
    if os.getenv("FULL_SEED", "true") == "true":
        print("Running full seed...")
        # Import seed logic
        from app.seed import seed as full_seed
        # Monkey patch seed to use sqlite
        full_seed()
    
    print("Demo DB ready")
finally:
    db.close()
