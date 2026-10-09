from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.api.routes.tasks import FINAL_STATUSES, _activity, _serialize, _visible_filter
from app.core.database import get_db
from app.core.deps import get_current_user, require_permission, require_roles
from app.models.alert import Alert, AlertSeverity
from app.models.batch import Batch
from app.models.product import Product
from app.models.task import Task, TaskChecklistItem
from app.models.user import User, UserRole
from app.services.audit import add_audit_log
from app.services.smart_markdown import build_markdown_suggestions

from app.services.plans import require_feature
router = APIRouter(dependencies=[Depends(require_feature("freshstock_today"))])


def _day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min).replace(tzinfo=timezone.utc)
    return start, start + timedelta(days=1)


def _add_system_task(db: Session, user: User, *, system_key: str, title: str, description: str,
                     task_type: str, priority: str, assigned_role: str | None,
                     product_id: int | None = None, batch_id: int | None = None,
                     location_id: int | None = None, quantity: Decimal | None = None,
                     checklist: list[str] | None = None) -> Task | None:
    existing = db.query(Task).filter(Task.tenant_id == user.tenant_id, Task.system_key == system_key).first()
    if existing:
        return None
    _, tomorrow = _day_bounds(date.today())
    task = Task(
        tenant_id=user.tenant_id,
        created_by_user_id=user.id,
        assigned_role=assigned_role,
        source="SYSTEM",
        system_key=system_key,
        task_type=task_type,
        title=title,
        description=description,
        priority=priority,
        status="TODO",
        product_id=product_id,
        batch_id=batch_id,
        location_id=location_id,
        quantity=quantity,
        due_at=tomorrow - timedelta(seconds=1),
        requires_scan=task_type in {"MARKDOWN", "EXPIRY_CHECK", "RESTOCK"},
    )
    db.add(task)
    db.flush()
    for position, text_value in enumerate(checklist or []):
        db.add(TaskChecklistItem(tenant_id=user.tenant_id, task_id=task.id, text=text_value, position=position))
    _activity(db, task, user.id, "SYSTEM_GENERATED", {"engine": "FRESHSTOCK_TODAY", "system_key": system_key})
    return task


def generate_today_tasks(db: Session, user: User, *, day: date | None = None) -> dict:
    day = day or date.today()
    prefix = f"TODAY:{day.isoformat()}"
    created: list[Task] = []

    expired = db.query(Batch).filter(
        Batch.tenant_id == user.tenant_id,
        Batch.quantity_available > 0,
        Batch.expiry_date < day,
    ).all()
    products = {p.id: p for p in db.query(Product).filter(Product.tenant_id == user.tenant_id).all()}
    for batch in expired:
        product = products.get(batch.product_id)
        if not product:
            continue
        task = _add_system_task(
            db, user,
            system_key=f"{prefix}:EXPIRED:{batch.id}",
            title=f"Wycofaj przeterminowaną partię: {product.name}",
            description=f"Partia {batch.batch_number}, termin {batch.expiry_date.isoformat()}, stan {batch.quantity_available} szt.",
            task_type="WASTE", priority="CRITICAL", assigned_role="WAREHOUSE",
            product_id=product.id, batch_id=batch.id, location_id=batch.warehouse_location_id,
            quantity=batch.quantity_available,
            checklist=["Potwierdź partię i lokalizację", "Zdejmij produkt ze sprzedaży", "Zarejestruj stratę"],
        )
        if task:
            created.append(task)

    for suggestion in build_markdown_suggestions(db, user.tenant_id, today=day)[:20]:
        task = _add_system_task(
            db, user,
            system_key=f"{prefix}:MARKDOWN:{suggestion['batch_id']}",
            title=f"Przecena: {suggestion['product_name']} −{suggestion['discount_percent']}%",
            description=(f"Smart Markdown proponuje {suggestion['suggested_price']:.2f} zamiast "
                         f"{suggestion['original_price']:.2f}. {suggestion['explanation']}. "
                         "Cena wymaga zatwierdzenia przez kierownika."),
            task_type="MARKDOWN", priority="CRITICAL" if suggestion["days_until_expiry"] <= 1 else "HIGH",
            assigned_role="EMPLOYEE", product_id=suggestion["product_id"], batch_id=suggestion["batch_id"],
            quantity=suggestion["at_risk_quantity"],
            checklist=["Zeskanuj właściwą partię", "Poproś kierownika o zatwierdzenie ceny", "Zmień oznaczenie ceny na półce"],
        )
        if task:
            created.append(task)

    stock_rows = db.query(
        Product,
        func.coalesce(func.sum(Batch.quantity_available), 0).label("stock"),
    ).outerjoin(Batch, (Batch.product_id == Product.id) & (Batch.tenant_id == user.tenant_id)).filter(
        Product.tenant_id == user.tenant_id,
        Product.is_active.is_(True),
    ).group_by(Product.id).all()
    for product, stock in stock_rows:
        stock = Decimal(stock or 0)
        if stock > Decimal(product.min_stock or 0):
            continue
        task = _add_system_task(
            db, user,
            system_key=f"{prefix}:RESTOCK:{product.id}",
            title=f"Uzupełnij stan: {product.name}",
            description=f"Stan {stock} szt., minimum {product.min_stock}, cel {product.target_stock}.",
            task_type="RESTOCK", priority="HIGH" if stock == 0 else "MEDIUM", assigned_role="WAREHOUSE",
            product_id=product.id, quantity=max(Decimal("0"), Decimal(product.target_stock or 0) - stock),
            checklist=["Sprawdź stan na zapleczu", "Uzupełnij półkę lub przygotuj zamówienie", "Potwierdź stan"],
        )
        if task:
            created.append(task)

    alerts = db.query(Alert).filter(
        Alert.tenant_id == user.tenant_id,
        Alert.is_resolved.is_(False),
        Alert.severity.in_([AlertSeverity.CRITICAL, AlertSeverity.HIGH]),
    ).order_by(Alert.created_at.desc()).limit(20).all()
    for alert in alerts:
        task = _add_system_task(
            db, user,
            system_key=f"{prefix}:ALERT:{alert.id}", title=alert.title, description=alert.message,
            task_type="GENERAL", priority="CRITICAL" if str(getattr(alert.severity, "value", alert.severity)) == "critical" else "HIGH",
            assigned_role="WAREHOUSE", product_id=alert.product_id, batch_id=alert.batch_id, location_id=alert.location_id,
        )
        if task:
            created.append(task)

    if created:
        add_audit_log(db, user_id=user.id, action="GENERATE", entity_type="freshstock_today", entity_id=day.isoformat(),
                      new_values={"task_ids": [task.id for task in created], "count": len(created)},
                      details="FreshStock Today wygenerował dzienny plan pracy")
    db.commit()
    return {"date": day.isoformat(), "created": len(created), "task_ids": [task.id for task in created]}


@router.post("/generate")
def generate_today(db: Session = Depends(get_db), current_user: User = Depends(require_roles(UserRole.OWNER, UserRole.MANAGER))):
    return generate_today_tasks(db, current_user)


@router.get("")
def get_today(db: Session = Depends(get_db), current_user: User = Depends(require_permission("dashboard:read"))):
    start, end = _day_bounds(date.today())
    priority_order = case((Task.priority == "CRITICAL", 0), (Task.priority == "HIGH", 1), (Task.priority == "MEDIUM", 2), else_=3)
    tasks = db.query(Task).filter(
        _visible_filter(current_user),
        Task.status.notin_(FINAL_STATUSES),
        (Task.due_at < end) | (Task.due_at.is_(None)),
    ).order_by(priority_order, Task.due_at.asc().nullslast()).limit(100).all()
    serialized = [_serialize(task) for task in tasks]
    return {
        "date": date.today().isoformat(),
        "tasks": serialized,
        "summary": {
            "total": len(serialized),
            "critical": sum(item["priority"] == "CRITICAL" for item in serialized),
            "overdue": sum(item["status"] == "OVERDUE" for item in serialized),
            "in_progress": sum(item["stored_status"] == "IN_PROGRESS" for item in serialized),
        },
    }
