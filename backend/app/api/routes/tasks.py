import os
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import and_, case, func, or_
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_roles
from app.models.batch import Batch
from app.models.location import WarehouseLocation
from app.models.product import Product
from app.models.task import Task, TaskActivityLog, TaskAttachment, TaskChecklistItem, TaskComment
from app.models.user import User, UserRole
from app.services.audit import add_audit_log

router = APIRouter()

TASK_TYPES = {"GENERAL", "EXPIRY_CHECK", "RESTOCK", "MARKDOWN", "WASTE", "INVENTORY_COUNT", "TRANSFER", "DELIVERY_CHECK", "CLEANING", "PRICE_CHECK", "RECALL", "CUSTOM"}
PRIORITIES = {"CRITICAL", "HIGH", "MEDIUM", "LOW"}
FINAL_STATUSES = {"COMPLETED", "SKIPPED", "CANCELLED"}
MANAGER_ROLES = {UserRole.OWNER.value, UserRole.MANAGER.value}


class TaskCreate(BaseModel):
    title: str = Field(min_length=3, max_length=255)
    description: Optional[str] = Field(default=None, max_length=5000)
    task_type: str = "GENERAL"
    priority: str = "MEDIUM"
    assigned_user_id: Optional[int] = None
    assigned_role: Optional[str] = None
    product_id: Optional[int] = None
    batch_id: Optional[int] = None
    location_id: Optional[int] = None
    quantity: Optional[Decimal] = Field(default=None, ge=0)
    due_at: Optional[datetime] = None
    requires_photo: bool = False
    requires_scan: bool = False
    requires_comment: bool = False
    checklist: list[str] = Field(default_factory=list, max_length=100)
    recurrence_rule: Optional[Literal["DAILY", "WEEKLY", "WEEKDAYS"]] = None
    recurrence_days: list[int] = Field(default_factory=list, max_length=7)
    source: Literal["OWNER", "MANAGER", "AI", "SYSTEM", "ALERT"] = "OWNER"

    @field_validator("title")
    @classmethod
    def strip_title(cls, value: str) -> str:
        return value.strip()

    @field_validator("task_type")
    @classmethod
    def valid_type(cls, value: str) -> str:
        value = value.upper()
        if value not in TASK_TYPES:
            raise ValueError("Nieprawidłowy typ zadania")
        return value

    @field_validator("priority")
    @classmethod
    def valid_priority(cls, value: str) -> str:
        value = value.upper()
        if value not in PRIORITIES:
            raise ValueError("Nieprawidłowy priorytet")
        return value

    @field_validator("assigned_role")
    @classmethod
    def valid_role(cls, value: Optional[str]) -> Optional[str]:
        if value is None or value == "":
            return None
        value = value.upper()
        if value not in {role.value for role in UserRole}:
            raise ValueError("Nieprawidłowa rola")
        return value

    @field_validator("recurrence_days")
    @classmethod
    def valid_days(cls, value: list[int]) -> list[int]:
        if any(day < 0 or day > 6 for day in value):
            raise ValueError("Dni powtarzania muszą mieścić się w zakresie 0–6")
        return sorted(set(value))


class TaskUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=3, max_length=255)
    description: Optional[str] = Field(default=None, max_length=5000)
    task_type: Optional[str] = None
    priority: Optional[str] = None
    assigned_user_id: Optional[int] = None
    assigned_role: Optional[str] = None
    product_id: Optional[int] = None
    batch_id: Optional[int] = None
    location_id: Optional[int] = None
    quantity: Optional[Decimal] = Field(default=None, ge=0)
    due_at: Optional[datetime] = None
    requires_photo: Optional[bool] = None
    requires_scan: Optional[bool] = None
    requires_comment: Optional[bool] = None


class CommentCreate(BaseModel):
    body: str = Field(min_length=1, max_length=5000)

    @field_validator("body")
    @classmethod
    def strip_body(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Komentarz nie może być pusty")
        return value


class ChecklistCreate(BaseModel):
    text: str = Field(min_length=1, max_length=500)


class BlockRequest(BaseModel):
    comment: str = Field(min_length=2, max_length=5000)


class ScanRequest(BaseModel):
    code: str = Field(min_length=3, max_length=100)


def _is_manager(user: User) -> bool:
    return str(user.role.value if hasattr(user.role, "value") else user.role) in MANAGER_ROLES


def _visible_filter(user: User):
    role = str(user.role.value if hasattr(user.role, "value") else user.role)
    if _is_manager(user):
        return Task.tenant_id == user.tenant_id
    return and_(
        Task.tenant_id == user.tenant_id,
        or_(
            Task.assigned_user_id == user.id,
            and_(Task.assigned_user_id.is_(None), Task.assigned_role == role),
            and_(Task.assigned_user_id.is_(None), Task.assigned_role.is_(None)),
        ),
    )


def _task_or_404(db: Session, task_id: int, user: User, *, manager_only: bool = False) -> Task:
    if manager_only and not _is_manager(user):
        raise HTTPException(status_code=403, detail="Brak uprawnień do zarządzania zadaniem")
    task = db.query(Task).filter(Task.id == task_id, _visible_filter(user)).first()
    if not task:
        raise HTTPException(status_code=404, detail="Zadanie nie istnieje")
    return task


def _effective_status(task: Task) -> str:
    now = datetime.now(timezone.utc)
    due = task.due_at
    if due and due.tzinfo is None:
        due = due.replace(tzinfo=timezone.utc)
    if task.status not in FINAL_STATUSES and due and due < now:
        return "OVERDUE"
    return task.status


def _activity(db: Session, task: Task, user_id: Optional[int], event: str, details: Optional[dict] = None) -> None:
    db.add(TaskActivityLog(tenant_id=task.tenant_id, task_id=task.id, user_id=user_id, event=event, details=details))


def _serialize(task: Task, detailed: bool = False) -> dict[str, Any]:
    checklist_done = sum(1 for item in task.checklist_items if item.is_completed)
    payload: dict[str, Any] = {
        "id": task.id,
        "tenant_id": task.tenant_id,
        "created_by_user_id": task.created_by_user_id,
        "created_by_name": task.creator.full_name if task.creator else None,
        "assigned_user_id": task.assigned_user_id,
        "assigned_user_name": task.assignee.full_name if task.assignee else None,
        "assigned_role": task.assigned_role,
        "source": task.source,
        "system_key": task.system_key,
        "task_type": task.task_type,
        "title": task.title,
        "description": task.description,
        "priority": task.priority,
        "status": _effective_status(task),
        "stored_status": task.status,
        "product_id": task.product_id,
        "product_name": task.product.name if task.product else None,
        "batch_id": task.batch_id,
        "batch_number": task.batch.batch_number if task.batch else None,
        "location_id": task.location_id,
        "location_name": task.location.name if task.location else None,
        "quantity": float(task.quantity) if task.quantity is not None else None,
        "due_at": task.due_at,
        "requires_photo": task.requires_photo,
        "requires_scan": task.requires_scan,
        "requires_comment": task.requires_comment,
        "recurrence_rule": task.recurrence_rule,
        "recurrence_days": task.recurrence_days or [],
        "started_at": task.started_at,
        "completed_at": task.completed_at,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
        "checklist_completed": checklist_done,
        "checklist_total": len(task.checklist_items),
        "comments_count": len(task.comments),
        "attachments_count": len(task.attachments),
    }
    if detailed:
        payload.update({
            "comments": [{"id": item.id, "body": item.body, "user_id": item.user_id, "user_name": item.user.full_name if item.user else None, "created_at": item.created_at} for item in task.comments],
            "attachments": [{"id": item.id, "file_name": item.file_name, "content_type": item.content_type, "size_bytes": item.size_bytes, "created_at": item.created_at, "download_url": f"/api/tasks/{task.id}/attachments/{item.id}"} for item in task.attachments],
            "checklist": [{"id": item.id, "text": item.text, "position": item.position, "is_completed": item.is_completed, "completed_at": item.completed_at} for item in task.checklist_items],
            "activity": [{"id": item.id, "event": item.event, "user_id": item.user_id, "user_name": item.user.full_name if item.user else None, "details": item.details, "created_at": item.created_at} for item in task.activity],
        })
    return payload


def _validate_relations(db: Session, payload: TaskCreate | TaskUpdate, tenant_id: int) -> None:
    if payload.assigned_user_id and not db.query(User.id).filter(User.id == payload.assigned_user_id, User.tenant_id == tenant_id, User.is_active.is_(True)).first():
        raise HTTPException(422, "Wybrany użytkownik nie istnieje w tym sklepie")
    for value, model, label in [
        (payload.product_id, Product, "Produkt"),
        (payload.batch_id, Batch, "Partia"),
        (payload.location_id, WarehouseLocation, "Lokalizacja"),
    ]:
        if value and not db.query(model.id).filter(model.id == value, model.tenant_id == tenant_id).first():
            raise HTTPException(422, f"{label} nie istnieje w tym sklepie")


def _next_due(task: Task) -> Optional[datetime]:
    if not task.recurrence_rule:
        return None
    base = task.due_at or datetime.now(timezone.utc)
    if base.tzinfo is None:
        base = base.replace(tzinfo=timezone.utc)
    if task.recurrence_rule == "DAILY":
        return base + timedelta(days=1)
    if task.recurrence_rule == "WEEKLY":
        return base + timedelta(days=7)
    allowed = task.recurrence_days or [0, 1, 2, 3, 4]
    for offset in range(1, 8):
        candidate = base + timedelta(days=offset)
        if candidate.weekday() in allowed:
            return candidate
    return base + timedelta(days=1)


def _create_next_occurrence(db: Session, task: Task, user_id: int) -> Optional[Task]:
    next_due = _next_due(task)
    if not next_due:
        return None
    root_id = task.recurrence_parent_id or task.id
    existing = db.query(Task.id).filter(Task.recurrence_parent_id == root_id, Task.due_at == next_due, Task.status.notin_(FINAL_STATUSES)).first()
    if existing:
        return None
    clone = Task(
        tenant_id=task.tenant_id, created_by_user_id=user_id, assigned_user_id=task.assigned_user_id,
        assigned_role=task.assigned_role, source="SYSTEM", task_type=task.task_type, title=task.title,
        description=task.description, priority=task.priority, status="TODO", product_id=task.product_id,
        batch_id=task.batch_id, location_id=task.location_id, quantity=task.quantity, due_at=next_due,
        requires_photo=task.requires_photo, requires_scan=task.requires_scan, requires_comment=task.requires_comment,
        recurrence_rule=task.recurrence_rule, recurrence_days=task.recurrence_days or [], recurrence_parent_id=root_id,
    )
    db.add(clone)
    db.flush()
    for item in task.checklist_items:
        db.add(TaskChecklistItem(tenant_id=task.tenant_id, task_id=clone.id, text=item.text, position=item.position))
    _activity(db, clone, user_id, "RECURRENCE_CREATED", {"previous_task_id": task.id})
    return clone


@router.get("")
def list_tasks(
    status_filter: Optional[str] = Query(None, alias="status"),
    mine: bool = False,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Task).filter(_visible_filter(current_user))
    if mine:
        query = query.filter(or_(Task.assigned_user_id == current_user.id, Task.assigned_user_id.is_(None)))
    if status_filter and status_filter != "OVERDUE":
        query = query.filter(Task.status == status_filter.upper())
    priority_order = case((Task.priority == "CRITICAL", 0), (Task.priority == "HIGH", 1), (Task.priority == "MEDIUM", 2), else_=3)
    tasks = query.order_by(priority_order, Task.due_at.asc().nullslast(), Task.created_at.desc()).limit(limit).all()
    result = [_serialize(task) for task in tasks]
    if status_filter == "OVERDUE":
        result = [task for task in result if task["status"] == "OVERDUE"]
    return result


@router.get("/summary")
def task_summary(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    tasks = db.query(Task).filter(_visible_filter(current_user)).all()
    serialized = [_serialize(task) for task in tasks]
    active = [task for task in serialized if task["status"] not in {"COMPLETED", "SKIPPED", "CANCELLED"}]
    counts = {key: sum(1 for task in serialized if task["status"] == key) for key in ["TODO", "IN_PROGRESS", "COMPLETED", "BLOCKED", "OVERDUE"]}
    today = datetime.now(timezone.utc).date()
    today_tasks = [task for task in serialized if task["due_at"] and (task["due_at"].date() if task["due_at"].tzinfo else task["due_at"].replace(tzinfo=timezone.utc).date()) == today]
    people: dict[int, dict[str, Any]] = {}
    if _is_manager(current_user):
        for task in serialized:
            if not task["assigned_user_id"]:
                continue
            row = people.setdefault(task["assigned_user_id"], {"user_id": task["assigned_user_id"], "name": task["assigned_user_name"], "total": 0, "completed": 0, "overdue": 0})
            row["total"] += 1
            row["completed"] += int(task["status"] == "COMPLETED")
            row["overdue"] += int(task["status"] == "OVERDUE")
    return {"total": len(serialized), "active": len(active), "today": len(today_tasks), "counts": counts, "by_user": list(people.values())}


@router.get("/{task_id}")
def get_task(task_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return _serialize(_task_or_404(db, task_id, current_user), detailed=True)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_task(payload: TaskCreate, db: Session = Depends(get_db), current_user: User = Depends(require_roles(UserRole.OWNER, UserRole.MANAGER))):
    _validate_relations(db, payload, current_user.tenant_id)
    source = payload.source if payload.source in {"AI", "SYSTEM", "ALERT"} else current_user.role.value
    task = Task(
        tenant_id=current_user.tenant_id, created_by_user_id=current_user.id,
        assigned_user_id=payload.assigned_user_id, assigned_role=None if payload.assigned_user_id else payload.assigned_role,
        source=source, task_type=payload.task_type, title=payload.title, description=payload.description,
        priority=payload.priority, status="TODO", product_id=payload.product_id, batch_id=payload.batch_id,
        location_id=payload.location_id, quantity=payload.quantity, due_at=payload.due_at,
        requires_photo=payload.requires_photo, requires_scan=payload.requires_scan, requires_comment=payload.requires_comment,
        recurrence_rule=payload.recurrence_rule, recurrence_days=payload.recurrence_days,
    )
    db.add(task)
    db.flush()
    for position, text_value in enumerate(payload.checklist):
        text_value = text_value.strip()
        if text_value:
            db.add(TaskChecklistItem(tenant_id=current_user.tenant_id, task_id=task.id, text=text_value, position=position))
    _activity(db, task, current_user.id, "CREATED", {"source": source})
    add_audit_log(db, user_id=current_user.id, action="CREATE", entity_type="task", entity_id=task.id, new_values={"title": task.title, "priority": task.priority, "assigned_user_id": task.assigned_user_id, "assigned_role": task.assigned_role})
    db.commit()
    db.refresh(task)
    return _serialize(task, detailed=True)


@router.patch("/{task_id}")
def update_task(task_id: int, payload: TaskUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    task = _task_or_404(db, task_id, current_user, manager_only=True)
    if task.status in FINAL_STATUSES:
        raise HTTPException(409, "Zakończonego zadania nie można edytować")
    _validate_relations(db, payload, current_user.tenant_id)
    changes = payload.model_dump(exclude_unset=True)
    if "task_type" in changes:
        changes["task_type"] = TaskCreate.valid_type(changes["task_type"])
    if "priority" in changes:
        changes["priority"] = TaskCreate.valid_priority(changes["priority"])
    if "assigned_role" in changes:
        changes["assigned_role"] = TaskCreate.valid_role(changes["assigned_role"])
    if changes.get("assigned_user_id"):
        changes["assigned_role"] = None
    old_values = {key: getattr(task, key) for key in changes}
    for key, value in changes.items():
        setattr(task, key, value)
    _activity(db, task, current_user.id, "UPDATED", changes)
    add_audit_log(db, user_id=current_user.id, action="UPDATE", entity_type="task", entity_id=task.id, old_values=old_values, new_values=changes)
    db.commit()
    return _serialize(task, detailed=True)


@router.post("/{task_id}/claim")
def claim_task(task_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    task = _task_or_404(db, task_id, current_user)
    if task.assigned_user_id and task.assigned_user_id != current_user.id:
        raise HTTPException(409, "Zadanie zostało już podjęte przez inną osobę")
    if task.status != "TODO":
        raise HTTPException(409, "Można podjąć tylko oczekujące zadanie")
    task.assigned_user_id = current_user.id
    _activity(db, task, current_user.id, "CLAIMED")
    db.commit()
    return _serialize(task, detailed=True)


@router.post("/{task_id}/start")
def start_task(task_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    task = _task_or_404(db, task_id, current_user)
    if task.assigned_user_id and task.assigned_user_id != current_user.id and not _is_manager(current_user):
        raise HTTPException(403, "To zadanie jest przypisane do innej osoby")
    if task.status not in {"TODO", "BLOCKED"}:
        raise HTTPException(409, "Tego zadania nie można rozpocząć")
    if not task.assigned_user_id:
        task.assigned_user_id = current_user.id
    task.status, task.started_at = "IN_PROGRESS", task.started_at or datetime.now(timezone.utc)
    _activity(db, task, current_user.id, "STARTED")
    db.commit()
    return _serialize(task, detailed=True)


@router.post("/{task_id}/scan")
def confirm_scan(task_id: int, payload: ScanRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    task = _task_or_404(db, task_id, current_user)
    if task.assigned_user_id not in {None, current_user.id} and not _is_manager(current_user):
        raise HTTPException(403, "To zadanie jest przypisane do innej osoby")
    _activity(db, task, current_user.id, "SCAN_CONFIRMED", {"code_suffix": payload.code[-4:], "code_length": len(payload.code)})
    db.commit()
    return {"message": "Skan został potwierdzony"}


@router.post("/{task_id}/complete")
def complete_task(task_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    task = _task_or_404(db, task_id, current_user)
    if task.assigned_user_id not in {None, current_user.id} and not _is_manager(current_user):
        raise HTTPException(403, "To zadanie jest przypisane do innej osoby")
    if task.status not in {"TODO", "IN_PROGRESS", "BLOCKED"}:
        raise HTTPException(409, "Tego zadania nie można zakończyć")
    if task.checklist_items and any(not item.is_completed for item in task.checklist_items):
        raise HTTPException(409, "Najpierw wykonaj wszystkie pozycje checklisty")
    if task.requires_photo and not task.attachments:
        raise HTTPException(409, "To zadanie wymaga dodania zdjęcia")
    if task.requires_comment and not any(item.user_id == current_user.id for item in task.comments):
        raise HTTPException(409, "To zadanie wymaga komentarza")
    if task.requires_scan and not any(item.event == "SCAN_CONFIRMED" for item in task.activity):
        raise HTTPException(409, "To zadanie wymaga potwierdzenia skanem")
    if not task.assigned_user_id:
        task.assigned_user_id = current_user.id
    task.status, task.completed_at = "COMPLETED", datetime.now(timezone.utc)
    _activity(db, task, current_user.id, "COMPLETED")
    _create_next_occurrence(db, task, current_user.id)
    add_audit_log(db, user_id=current_user.id, action="COMPLETE", entity_type="task", entity_id=task.id, new_values={"status": "COMPLETED"})
    db.commit()
    return _serialize(task, detailed=True)


@router.post("/{task_id}/block")
def block_task(task_id: int, payload: BlockRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    task = _task_or_404(db, task_id, current_user)
    if task.status in FINAL_STATUSES:
        raise HTTPException(409, "Zadanie jest już zakończone")
    if not task.assigned_user_id:
        task.assigned_user_id = current_user.id
    comment = TaskComment(tenant_id=task.tenant_id, task_id=task.id, user_id=current_user.id, body=payload.comment.strip())
    db.add(comment)
    task.status = "BLOCKED"
    _activity(db, task, current_user.id, "BLOCKED", {"comment": payload.comment.strip()})
    db.commit()
    return _serialize(task, detailed=True)


@router.post("/{task_id}/cancel")
def cancel_task(task_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    task = _task_or_404(db, task_id, current_user, manager_only=True)
    if task.status in FINAL_STATUSES:
        raise HTTPException(409, "Zadanie jest już zakończone")
    task.status = "CANCELLED"
    _activity(db, task, current_user.id, "CANCELLED")
    add_audit_log(db, user_id=current_user.id, action="CANCEL", entity_type="task", entity_id=task.id, new_values={"status": "CANCELLED"})
    db.commit()
    return _serialize(task, detailed=True)


@router.post("/{task_id}/skip")
def skip_task(task_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    task = _task_or_404(db, task_id, current_user, manager_only=True)
    if task.status in FINAL_STATUSES:
        raise HTTPException(409, "Zadanie jest już zakończone")
    task.status, task.completed_at = "SKIPPED", datetime.now(timezone.utc)
    _activity(db, task, current_user.id, "SKIPPED")
    _create_next_occurrence(db, task, current_user.id)
    add_audit_log(db, user_id=current_user.id, action="SKIP", entity_type="task", entity_id=task.id, new_values={"status": "SKIPPED"})
    db.commit()
    return _serialize(task, detailed=True)


@router.post("/{task_id}/comments", status_code=status.HTTP_201_CREATED)
def add_comment(task_id: int, payload: CommentCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    task = _task_or_404(db, task_id, current_user)
    comment = TaskComment(tenant_id=task.tenant_id, task_id=task.id, user_id=current_user.id, body=payload.body)
    db.add(comment)
    _activity(db, task, current_user.id, "COMMENTED")
    db.commit()
    db.refresh(comment)
    return {"id": comment.id, "body": comment.body, "user_id": comment.user_id, "user_name": current_user.full_name, "created_at": comment.created_at}


@router.post("/{task_id}/checklist", status_code=status.HTTP_201_CREATED)
def add_checklist_item(task_id: int, payload: ChecklistCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    task = _task_or_404(db, task_id, current_user, manager_only=True)
    position = (db.query(func.max(TaskChecklistItem.position)).filter(TaskChecklistItem.task_id == task.id).scalar() or -1) + 1
    item = TaskChecklistItem(tenant_id=task.tenant_id, task_id=task.id, text=payload.text.strip(), position=position)
    db.add(item)
    _activity(db, task, current_user.id, "CHECKLIST_ITEM_ADDED", {"text": item.text})
    db.commit()
    db.refresh(item)
    return {"id": item.id, "text": item.text, "position": item.position, "is_completed": False}


@router.patch("/{task_id}/checklist/{item_id}")
def toggle_checklist_item(task_id: int, item_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    task = _task_or_404(db, task_id, current_user)
    item = db.query(TaskChecklistItem).filter(TaskChecklistItem.id == item_id, TaskChecklistItem.task_id == task.id).first()
    if not item:
        raise HTTPException(404, "Pozycja checklisty nie istnieje")
    item.is_completed = not item.is_completed
    item.completed_by_user_id = current_user.id if item.is_completed else None
    item.completed_at = datetime.now(timezone.utc) if item.is_completed else None
    _activity(db, task, current_user.id, "CHECKLIST_CHANGED", {"item_id": item.id, "completed": item.is_completed})
    db.commit()
    return {"id": item.id, "is_completed": item.is_completed, "completed_at": item.completed_at}


def _s3_client():
    try:
        import boto3
        from botocore.config import Config
    except ImportError as exc:
        raise HTTPException(503, "Obsługa zdjęć nie jest dostępna") from exc
    required = ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_ENDPOINT_URL_S3", "AWS_REGION"]
    if any(not os.getenv(name) for name in required):
        raise HTTPException(503, "Magazyn zdjęć nie został skonfigurowany")
    return boto3.client(
        "s3", endpoint_url=os.environ["AWS_ENDPOINT_URL_S3"], region_name=os.environ["AWS_REGION"],
        aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"], aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
        config=Config(s3={"addressing_style": "path"}, signature_version="s3v4"),
    )


@router.post("/{task_id}/attachments", status_code=status.HTTP_201_CREATED)
async def upload_attachment(task_id: int, file: UploadFile = File(...), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    task = _task_or_404(db, task_id, current_user)
    if file.content_type not in {"image/jpeg", "image/png", "image/webp"}:
        raise HTTPException(422, "Dozwolone są zdjęcia JPG, PNG i WEBP")
    content = await file.read(4 * 1024 * 1024 + 1)
    if len(content) > 4 * 1024 * 1024:
        raise HTTPException(413, "Zdjęcie może mieć maksymalnie 4 MB")
    if not content:
        raise HTTPException(422, "Plik jest pusty")
    signatures = {
        "image/jpeg": content.startswith(b"\xff\xd8\xff"),
        "image/png": content.startswith(b"\x89PNG\r\n\x1a\n"),
        "image/webp": content.startswith(b"RIFF") and len(content) >= 12 and content[8:12] == b"WEBP",
    }
    if not signatures.get(file.content_type, False):
        raise HTTPException(422, "Zawartość pliku nie odpowiada formatowi zdjęcia")
    suffix = Path(file.filename or "photo.jpg").suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
        suffix = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}[file.content_type]
    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", Path(file.filename or f"photo{suffix}").name)[:255]
    object_key = f"tenants/{task.tenant_id}/tasks/{task.id}/{uuid4().hex}{suffix}"
    bucket = os.getenv("TASK_ATTACHMENTS_BUCKET", "task-attachments")
    _s3_client().put_object(Bucket=bucket, Key=object_key, Body=content, ContentType=file.content_type, CacheControl="private, max-age=300")
    attachment = TaskAttachment(tenant_id=task.tenant_id, task_id=task.id, uploaded_by_user_id=current_user.id, object_key=object_key, file_name=safe_name, content_type=file.content_type, size_bytes=len(content))
    db.add(attachment)
    _activity(db, task, current_user.id, "PHOTO_ADDED", {"file_name": safe_name})
    db.commit()
    db.refresh(attachment)
    return {"id": attachment.id, "file_name": attachment.file_name, "content_type": attachment.content_type, "size_bytes": attachment.size_bytes, "download_url": f"/api/tasks/{task.id}/attachments/{attachment.id}"}


@router.get("/{task_id}/attachments/{attachment_id}")
def download_attachment(task_id: int, attachment_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    task = _task_or_404(db, task_id, current_user)
    attachment = db.query(TaskAttachment).filter(TaskAttachment.id == attachment_id, TaskAttachment.task_id == task.id).first()
    if not attachment:
        raise HTTPException(404, "Zdjęcie nie istnieje")
    bucket = os.getenv("TASK_ATTACHMENTS_BUCKET", "task-attachments")
    url = _s3_client().generate_presigned_url("get_object", Params={"Bucket": bucket, "Key": attachment.object_key}, ExpiresIn=900)
    return {"url": url, "expires_in": 900}
