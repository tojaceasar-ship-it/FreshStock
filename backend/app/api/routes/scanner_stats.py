from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_roles
from app.models.scan_event import ScanEvent
from app.models.user import User, UserRole


router = APIRouter()


class ScanEventCreate(BaseModel):
    device_id: str = Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9._-]+$")
    context: Literal["product", "inventory"]
    outcome: Literal["accepted", "rejected", "not_found", "error"]
    barcode_format: Optional[str] = Field(default=None, max_length=30)
    code_length: Optional[int] = Field(default=None, ge=0, le=128)
    duration_ms: Optional[int] = Field(default=None, ge=0, le=120000)
    error_reason: Optional[str] = Field(default=None, max_length=100)
    platform: Optional[str] = Field(default=None, max_length=30)


@router.post("/events", status_code=202)
def record_scan_event(payload: ScanEventCreate, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    event = ScanEvent(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        device_id=payload.device_id,
        context=payload.context,
        outcome=payload.outcome,
        barcode_format=payload.barcode_format,
        code_length=payload.code_length,
        duration_ms=payload.duration_ms,
        error_reason=payload.error_reason,
        platform=payload.platform,
        user_agent=(request.headers.get("user-agent") or "")[:500] or None,
    )
    db.add(event)
    db.commit()
    return {"accepted": True}


@router.get("/stats")
def scan_stats(
    days: int = Query(30, ge=1, le=90),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.OWNER, UserRole.MANAGER)),
):
    since = datetime.now(timezone.utc) - timedelta(days=days)
    base = [ScanEvent.tenant_id == current_user.tenant_id, ScanEvent.created_at >= since]
    outcomes = db.query(ScanEvent.outcome, func.count(ScanEvent.id)).filter(*base).group_by(ScanEvent.outcome).all()
    outcome_counts = {name: int(count) for name, count in outcomes}
    devices = db.query(
        ScanEvent.device_id,
        ScanEvent.platform,
        func.count(ScanEvent.id).label("total"),
        func.sum(case((ScanEvent.outcome == "accepted", 1), else_=0)).label("accepted"),
        func.max(ScanEvent.created_at).label("last_seen"),
    ).filter(*base).group_by(ScanEvent.device_id, ScanEvent.platform).order_by(func.count(ScanEvent.id).desc()).limit(100).all()
    total = sum(outcome_counts.values())
    accepted = outcome_counts.get("accepted", 0)
    return {
        "days": days,
        "total": total,
        "accepted": accepted,
        "rejected": total - accepted,
        "success_rate": round((accepted / total) * 100, 1) if total else 0,
        "outcomes": outcome_counts,
        "devices": [
            {
                "device_id": row.device_id,
                "platform": row.platform or "unknown",
                "total": int(row.total or 0),
                "accepted": int(row.accepted or 0),
                "success_rate": round((int(row.accepted or 0) / int(row.total)) * 100, 1) if row.total else 0,
                "last_seen": row.last_seen,
            }
            for row in devices
        ],
    }
