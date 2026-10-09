from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_roles
from app.models.subscription import Plan, SubscriptionEvent, SubscriptionStatus, TenantStore
from app.models.user import User, UserRole
from app.services.audit import add_audit_log
from app.services.plans import PLAN_FEATURES, PLAN_LIMITS, PLAN_PRICES, PlanService

router = APIRouter()


class PlanChange(BaseModel):
    plan: Plan


class StoreCreate(BaseModel):
    name: str
    code: str


def _capabilities(db: Session, user: User):
    sub = PlanService.subscription(db, user.tenant_id)
    used, limits = PlanService.usage(db, user.tenant_id), PlanService.limits(db, user.tenant_id)
    return {
        "plan": sub.plan, "status": sub.status, "billing_cycle": sub.billing_cycle,
        "trial_ends_at": sub.trial_ends_at, "current_period_start": sub.current_period_start,
        "current_period_end": sub.current_period_end, "cancel_at_period_end": sub.cancel_at_period_end,
        "price_monthly": PLAN_PRICES.get(sub.plan),
        "features": {name: PlanService.has_feature(db, user.tenant_id, name) for name in sorted(set().union(*PLAN_FEATURES.values()))},
        "limits": {key: {"used": used.get(key, 0), "max": value} for key, value in limits.items()},
    }


@router.get("/plans")
def plans():
    return [{"plan": name, "price_monthly": PLAN_PRICES[name], "limits": PLAN_LIMITS[name], "features": sorted(PLAN_FEATURES[name])} for name in Plan]


@router.get("")
def current(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _capabilities(db, user)


@router.get("/usage")
def usage(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _capabilities(db, user)["limits"]


@router.get("/history")
def history(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.query(SubscriptionEvent).filter(SubscriptionEvent.tenant_id == user.tenant_id).order_by(SubscriptionEvent.created_at.desc()).all()


@router.post("/change-plan")
def change_plan(payload: PlanChange, db: Session = Depends(get_db), user: User = Depends(require_roles(UserRole.OWNER))):
    sub = PlanService.subscription(db, user.tenant_id)
    target = payload.plan.value
    usage, limits = PlanService.usage(db, user.tenant_id), PLAN_LIMITS[target]
    exceeded = {key: {"used": usage.get(key, 0), "max": maximum} for key, maximum in limits.items() if maximum is not None and usage.get(key, 0) > maximum}
    if exceeded:
        raise HTTPException(status_code=409, detail={"error": "DOWNGRADE_BLOCKED", "target_plan": target, "exceeded": exceeded})
    old = sub.plan
    if old == target:
        return _capabilities(db, user)
    order = ["STANDARD", "PRO", "BUSINESS", "ENTERPRISE"]
    event_type = "UPGRADE" if order.index(target) > order.index(old) else "DOWNGRADE"
    sub.plan, sub.status, sub.cancel_at_period_end = target, SubscriptionStatus.ACTIVE.value, False
    db.add(SubscriptionEvent(tenant_id=user.tenant_id, old_plan=old, new_plan=target, event_type=event_type, created_by=user.id))
    add_audit_log(db, user_id=user.id, action=event_type, entity_type="subscription", entity_id=sub.id, old_values={"plan": old}, new_values={"plan": target})
    db.commit()
    return _capabilities(db, user)


@router.post("/cancel")
def cancel(db: Session = Depends(get_db), user: User = Depends(require_roles(UserRole.OWNER))):
    sub = PlanService.subscription(db, user.tenant_id)
    sub.cancel_at_period_end = True
    db.add(SubscriptionEvent(tenant_id=user.tenant_id, old_plan=sub.plan, new_plan=sub.plan, event_type="CANCEL", created_by=user.id))
    add_audit_log(db, user_id=user.id, action="CANCEL", entity_type="subscription", entity_id=sub.id)
    db.commit()
    return _capabilities(db, user)


@router.post("/reactivate")
def reactivate(db: Session = Depends(get_db), user: User = Depends(require_roles(UserRole.OWNER))):
    sub = PlanService.subscription(db, user.tenant_id)
    sub.cancel_at_period_end, sub.status = False, SubscriptionStatus.ACTIVE.value
    db.add(SubscriptionEvent(tenant_id=user.tenant_id, old_plan=sub.plan, new_plan=sub.plan, event_type="REACTIVATE", created_by=user.id))
    add_audit_log(db, user_id=user.id, action="REACTIVATE", entity_type="subscription", entity_id=sub.id)
    db.commit()
    return _capabilities(db, user)


@router.get("/stores")
def stores(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.query(TenantStore).filter(TenantStore.tenant_id == user.tenant_id).order_by(TenantStore.id).all()


@router.post("/stores")
def create_store(payload: StoreCreate, db: Session = Depends(get_db), user: User = Depends(require_roles(UserRole.OWNER))):
    PlanService.assert_limit(db, user.tenant_id, "stores")
    if not PlanService.has_feature(db, user.tenant_id, "multi_store"):
        raise HTTPException(status_code=403, detail={"error": "FEATURE_NOT_AVAILABLE", "feature": "multi_store", "required_plan": "BUSINESS"})
    if db.query(TenantStore).filter(TenantStore.tenant_id == user.tenant_id, TenantStore.code == payload.code).first():
        raise HTTPException(status_code=409, detail="Kod sklepu już istnieje")
    row = TenantStore(tenant_id=user.tenant_id, name=payload.name.strip(), code=payload.code.strip().upper())
    db.add(row); db.commit(); db.refresh(row)
    return row


def capabilities(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _capabilities(db, user)
