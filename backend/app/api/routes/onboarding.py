import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_permission, require_roles
from app.core.security import get_password_hash
from app.integrations.models import POSIntegration
from app.models.location import LocationType, WarehouseLocation
from app.models.onboarding import BusinessPriority, NotificationSettings, OnboardingProgress, SetupTask, StoreSettings
from app.models.product import Product
from app.models.supplier import Supplier
from app.models.user import User, UserRole

router = APIRouter()

BUSINESS_TYPES = {"GROCERY", "MINIMARKET", "SUPERMARKET", "BAKERY", "BUTCHER", "FRUIT_VEGETABLES", "DELICATESSEN", "CONVENIENCE", "WHOLESALE", "OTHER"}
PRESETS = {
    "GROCERY": {"fefo_enabled": True, "expiry_tracking": True, "waste_tracking": True, "markdown_suggestions_enabled": True},
    "BAKERY": {"fefo_enabled": True, "expiry_tracking": True, "waste_tracking": True, "high_frequency_waste_tracking": True},
    "BUTCHER": {"fefo_enabled": True, "expiry_tracking": True, "waste_tracking": True, "batch_tracking": "ALWAYS"},
    "DELICATESSEN": {"fefo_enabled": True, "expiry_tracking": True, "waste_tracking": True},
    "WHOLESALE": {"batch_tracking": "ALWAYS", "expiry_tracking": False},
}
LOCATION_TYPES = {"SALES_FLOOR": LocationType.STORE, "MAIN_WAREHOUSE": LocationType.WAREHOUSE, "COLD_ROOM": LocationType.FRIDGE,
                  "FREEZER": LocationType.FREEZER, "BACKROOM": LocationType.BACKROOM, "VEGETABLES_STORAGE": LocationType.WAREHOUSE,
                  "DRINKS_STORAGE": LocationType.WAREHOUSE, "OTHER": LocationType.OTHER}
TASKS = [("IMPORT_PRODUCTS", "Importuj produkty"), ("ADD_SUPPLIERS", "Dodaj dostawców"),
         ("VERIFY_LOCATIONS", "Sprawdź lokalizacje magazynowe"), ("OPENING_STOCK", "Wprowadź stan początkowy"),
         ("CONNECT_POS", "Połącz system sprzedaży"), ("FIRST_INVENTORY", "Przeprowadź pierwszą inwentaryzację")]


class StepSave(BaseModel):
    data: Dict[str, Any] = Field(default_factory=dict)
    complete: bool = True
    next_step: Optional[int] = Field(default=None, ge=1, le=14)


class TaskUpdate(BaseModel):
    status: Literal["TODO", "DONE", "SKIPPED"]


class ProductRows(BaseModel):
    rows: List[Dict[str, Any]] = Field(max_length=5000)


def _product_preview(db: Session, rows: List[Dict[str, Any]]):
    result = []
    seen_sku, seen_ean = set(), set()
    for number, raw in enumerate(rows, 1):
        sku, ean, name = str(raw.get("sku", "")).strip(), str(raw.get("ean", "")).strip() or None, str(raw.get("name", "")).strip()
        errors = []
        if not sku: errors.append("Brak SKU")
        if not name: errors.append("Brak nazwy")
        duplicate = (sku and (sku in seen_sku or db.query(Product.id).filter(Product.sku == sku).first())) or (ean and (ean in seen_ean or db.query(Product.id).filter(Product.ean == ean).first()))
        if duplicate: errors.append("SKU lub EAN już istnieje")
        seen_sku.add(sku); ean and seen_ean.add(ean)
        try:
            purchase_price, selling_price = float(raw.get("purchase_price", 0)), float(raw.get("selling_price", 0))
        except (TypeError, ValueError):
            purchase_price = selling_price = 0; errors.append("Nieprawidłowa cena")
        result.append({"row": number, "sku": sku, "ean": ean, "name": name, "purchase_price": purchase_price, "selling_price": selling_price, "valid": not errors, "errors": errors})
    return result


def _state(db: Session, tenant_id: int):
    settings = db.query(StoreSettings).filter_by(tenant_id=tenant_id).first()
    if not settings:
        settings = StoreSettings(tenant_id=tenant_id, expiry_rules=[], markdown_rules=[], dashboard_layout=[])
        db.add(settings)
    progress = db.query(OnboardingProgress).filter_by(tenant_id=tenant_id).first()
    if not progress:
        progress = OnboardingProgress(tenant_id=tenant_id, current_step=1, completed_steps=[], step_data={}, status="NOT_STARTED")
        db.add(progress)
    db.flush()
    return settings, progress


def _serialize(db: Session, tenant_id: int, settings: StoreSettings, progress: OnboardingProgress):
    return {
        "status": progress.status, "current_step": progress.current_step,
        "completed_steps": progress.completed_steps or [], "step_data": progress.step_data or {},
        "settings": {c.name: getattr(settings, c.name) for c in settings.__table__.columns if c.name not in {"id", "tenant_id"}},
        "priorities": [x.priority for x in db.query(BusinessPriority).filter_by(tenant_id=tenant_id).all()],
        "notifications": (lambda n: {"alert_rules": n.alert_rules, "channels": n.channels} if n else None)(db.query(NotificationSettings).filter_by(tenant_id=tenant_id).first()),
        "locations": [{"id": x.id, "name": x.name, "code": x.code, "type": x.type.value if hasattr(x.type, "value") else x.type}
                      for x in db.query(WarehouseLocation).filter_by(tenant_id=tenant_id).order_by(WarehouseLocation.name).all()],
        "tasks": [{"id": x.id, "task_key": x.task_key, "label": x.label, "status": x.status, "is_important": x.is_important}
                  for x in db.query(SetupTask).filter_by(tenant_id=tenant_id).order_by(SetupTask.id).all()],
    }


@router.get("")
def get_onboarding(db: Session = Depends(get_db), current_user: User = Depends(require_permission("onboarding:read"))):
    settings, progress = _state(db, current_user.tenant_id)
    db.commit()
    return _serialize(db, current_user.tenant_id, settings, progress)


@router.put("/steps/{step}")
def save_step(step: int, payload: StepSave, db: Session = Depends(get_db), current_user: User = Depends(require_roles(UserRole.OWNER))):
    if step < 1 or step > 14:
        raise HTTPException(400, "Nieprawidłowy krok")
    tenant_id, data = current_user.tenant_id, payload.data
    settings, progress = _state(db, tenant_id)
    if not payload.complete:
        step_data = dict(progress.step_data or {}); step_data[str(step)] = data; progress.step_data = step_data
        if progress.status != "COMPLETED":
            progress.status = "IN_PROGRESS"
        progress.current_step = payload.next_step or step
        db.commit()
        return _serialize(db, tenant_id, settings, progress)
    if step == 1:
        business_type = str(data.get("business_type", "")).upper()
        if business_type not in BUSINESS_TYPES:
            raise HTTPException(422, "Wybierz prawidłowy typ sklepu")
        settings.business_type = business_type
        for key, value in PRESETS.get(business_type, {}).items():
            setattr(settings, key, value)
    elif step == 2:
        if not data.get("store_name") or not data.get("country") or not data.get("currency") or not data.get("timezone") or not data.get("language"):
            raise HTTPException(422, "Uzupełnij wymagane dane sklepu")
        if data.get("vat_number") and not re.fullmatch(r"[A-Za-z0-9 -]{5,20}", str(data["vat_number"])):
            raise HTTPException(422, "Nieprawidłowy numer VAT")
        for key in ["store_name", "company_name", "address", "vat_number", "country", "currency", "timezone", "language", "store_size", "employee_count", "approximate_sku_count", "pos_count"]:
            if key in data: setattr(settings, key, data[key] or None)
    elif step == 3:
        locations = data.get("locations", [])
        if not locations: raise HTTPException(422, "Wybierz co najmniej jedną lokalizację")
        for index, item in enumerate(locations):
            key = str(item.get("key", "OTHER")).upper()
            name = str(item.get("name", "")).strip()
            if not name: raise HTTPException(422, "Każda lokalizacja musi mieć nazwę")
            code = f"T{tenant_id}-{key[:12]}-{index + 1}"
            loc = db.query(WarehouseLocation).filter_by(tenant_id=tenant_id, code=code).first()
            if loc: loc.name, loc.type = name, LOCATION_TYPES.get(key, LocationType.OTHER)
            else: db.add(WarehouseLocation(tenant_id=tenant_id, name=name, code=code, type=LOCATION_TYPES.get(key, LocationType.OTHER)))
    elif step == 4:
        rules = sorted(set(int(x) for x in data.get("expiry_rules", []) if int(x) >= 0), reverse=True)
        if not rules: raise HTTPException(422, "Podaj co najmniej jeden próg ważności")
        settings.expiry_rules, settings.expiry_tracking = rules, True
    elif step == 5:
        settings.fefo_enabled = bool(data.get("fefo_enabled"))
    elif step == 6:
        settings.markdown_suggestions_enabled = bool(data.get("enabled"))
        rules = data.get("rules", [])
        if settings.markdown_suggestions_enabled and not rules: raise HTTPException(422, "Dodaj regułę przeceny")
        settings.markdown_rules = rules
    elif step == 7:
        settings.delivery_frequency = data.get("delivery_frequency")
        settings.require_expiry_on_receiving = data.get("require_expiry_on_receiving")
        settings.batch_tracking = data.get("batch_tracking")
    elif step == 8:
        settings.sales_method, settings.selected_pos_provider = data.get("sales_method"), data.get("provider")
        provider = data.get("provider")
        if provider and not db.query(POSIntegration).filter_by(tenant_id=tenant_id, provider=provider).first():
            db.add(POSIntegration(tenant_id=tenant_id, provider=provider, name=f"{provider.replace('_', ' ').title()} (do konfiguracji)", status="DISABLED", sync_mode="CSV" if provider == "generic_csv" else "POLLING"))
    elif step == 9:
        settings.product_import_method = data.get("method")
    elif step == 10 and data.get("supplier"):
        supplier = data["supplier"]
        if not supplier.get("name"): raise HTTPException(422, "Nazwa dostawcy jest wymagana")
        existing_supplier = db.query(Supplier).filter(Supplier.name == supplier["name"])
        if supplier.get("vat_number"):
            existing_supplier = existing_supplier.filter(Supplier.vat_number == supplier["vat_number"])
        if not existing_supplier.first():
            db.add(Supplier(name=supplier["name"], email=supplier.get("email"), phone=supplier.get("phone"), vat_number=supplier.get("vat_number"), address=supplier.get("address")))
    elif step == 11:
        for invite in data.get("users", []):
            role = str(invite.get("role", "VIEWER")).upper()
            if role not in {x.value for x in UserRole}: raise HTTPException(422, f"Nieprawidłowa rola: {role}")
            if role == "OWNER": role = "MANAGER"
            email = str(invite.get("email", "")).lower().strip()
            password = str(invite.get("password", ""))
            if not email or len(password) < 12: raise HTTPException(422, "Email i hasło (minimum 12 znaków) są wymagane")
            if db.query(User).filter(User.email == email).first(): continue
            base_username = invite.get("username") or email.split("@")[0]
            username, suffix = base_username, 1
            while db.query(User.id).filter(User.username == username).first():
                suffix += 1; username = f"{base_username}{suffix}"
            db.add(User(tenant_id=tenant_id, email=email, username=username, full_name=invite.get("full_name") or email,
                        hashed_password=get_password_hash(password), role=UserRole(role)))
    elif step == 12:
        notification = db.query(NotificationSettings).filter_by(tenant_id=tenant_id).first()
        if not notification:
            notification = NotificationSettings(tenant_id=tenant_id); db.add(notification)
        notification.alert_rules, notification.channels = data.get("alert_rules", {}), data.get("channels", ["IN_APP"])
    elif step == 13:
        priorities = list(dict.fromkeys(data.get("business_priorities", [])))
        db.query(BusinessPriority).filter_by(tenant_id=tenant_id).delete(synchronize_session=False)
        db.add_all([BusinessPriority(tenant_id=tenant_id, priority=x) for x in priorities])
        order = []
        if "EXPIRY_WASTE" in priorities: order += ["EXPIRY_RISK", "WASTE", "MARKDOWN_OPPORTUNITIES"]
        if "STOCKOUTS" in priorities: order += ["LOW_STOCK", "DAYS_UNTIL_STOCKOUT", "REORDER_SUGGESTIONS"]
        settings.dashboard_layout = list(dict.fromkeys(order))
    elif step == 14 and payload.complete:
        progress.status, progress.completed_at, progress.current_step = "COMPLETED", datetime.now(timezone.utc), 14
        for task_key, label in TASKS:
            if not db.query(SetupTask).filter_by(tenant_id=tenant_id, task_key=task_key).first():
                db.add(SetupTask(tenant_id=tenant_id, task_key=task_key, label=label))

    step_data = dict(progress.step_data or {}); step_data[str(step)] = data; progress.step_data = step_data
    completed = set(progress.completed_steps or [])
    if payload.complete: completed.add(step)
    progress.completed_steps = sorted(completed)
    if progress.status != "COMPLETED": progress.status = "IN_PROGRESS"
    progress.current_step = payload.next_step or (min(step + 1, 14) if payload.complete else step)
    db.commit()
    return _serialize(db, tenant_id, settings, progress)


@router.patch("/tasks/{task_id}")
def update_task(task_id: int, payload: TaskUpdate, db: Session = Depends(get_db), current_user: User = Depends(require_roles(UserRole.OWNER, UserRole.MANAGER))):
    task = db.query(SetupTask).filter_by(id=task_id, tenant_id=current_user.tenant_id).first()
    if not task: raise HTTPException(404, "Zadanie nie istnieje")
    task.status = payload.status; db.commit()
    return {"id": task.id, "status": task.status}


@router.get("/dashboard")
def onboarding_dashboard(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    settings, progress = _state(db, current_user.tenant_id)
    tasks = db.query(SetupTask).filter_by(tenant_id=current_user.tenant_id).all()
    important = [x for x in tasks if x.is_important]
    percent = round(100 * sum(x.status in {"DONE", "SKIPPED"} for x in important) / len(important)) if important else (100 if progress.status == "COMPLETED" else 0)
    return {"onboarding_status": progress.status, "setup_percent": percent, "dashboard_layout": settings.dashboard_layout or [],
            "tasks": [{"id": x.id, "label": x.label, "status": x.status} for x in tasks]}


@router.post("/products/preview")
def preview_products(payload: ProductRows, db: Session = Depends(get_db), current_user: User = Depends(require_roles(UserRole.OWNER))):
    rows = _product_preview(db, payload.rows)
    return {"rows": rows, "valid": sum(x["valid"] for x in rows), "invalid": sum(not x["valid"] for x in rows)}


@router.post("/products/import")
def import_products(payload: ProductRows, db: Session = Depends(get_db), current_user: User = Depends(require_roles(UserRole.OWNER))):
    rows = _product_preview(db, payload.rows); created = []
    for row in rows:
        if not row["valid"]: continue
        product = Product(sku=row["sku"], ean=row["ean"], name=row["name"], purchase_price=row["purchase_price"], selling_price=row["selling_price"])
        db.add(product); created.append(row["sku"])
    db.commit()
    return {"created": len(created), "skipped": len(rows) - len(created), "created_skus": created, "rows": rows}
