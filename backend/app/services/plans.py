from datetime import datetime, timezone
from typing import Any

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.onboarding import StoreSettings
from app.models.product import Product
from app.models.subscription import Plan, Subscription, SubscriptionOverride, SubscriptionStatus, TenantStore
from app.models.user import User


STANDARD = {
    "products", "categories", "suppliers", "batches", "expiry_tracking", "fefo", "inventory",
    "locations", "deliveries", "purchase_orders", "waste", "scanner", "inventory_count",
    "basic_alerts", "basic_reports", "csv_import_export", "open_food_facts", "basic_tasks", "generic_csv_pos",
}
PRO = STANDARD | {
    "shelf_mode", "advanced_tasks", "freshstock_today", "smart_markdown", "ai_restock", "ai_markdown",
    "ai_waste_prediction", "savings_dashboard", "advanced_reports", "generic_rest", "webhooks_basic",
    "task_checklists", "task_photos", "task_comments", "recurring_tasks", "realtime_pos",
}
BUSINESS = PRO | {
    "multi_store", "central_dashboard", "inter_store_transfers", "multiple_pos_integrations",
    "freshstock_bridge", "api_access", "webhooks", "advanced_rbac", "full_audit_log",
    "full_traceability", "cross_store_reports", "store_comparison", "central_purchase_management",
}
ENTERPRISE = BUSINESS | {
    "custom_pos_integrations", "sso_saml", "dedicated_onboarding", "custom_api", "custom_reports",
    "sla", "priority_support", "erp_integrations", "accounting_integrations", "custom_security_requirements",
}

PLAN_FEATURES = {Plan.STANDARD.value: STANDARD, Plan.PRO.value: PRO, Plan.BUSINESS.value: BUSINESS, Plan.ENTERPRISE.value: ENTERPRISE}
PLAN_LIMITS = {
    Plan.STANDARD.value: {"stores": 1, "users": 5, "sku": 5000, "pos_integrations": 0},
    Plan.PRO.value: {"stores": 1, "users": 15, "sku": 25000, "pos_integrations": 1},
    Plan.BUSINESS.value: {"stores": 5, "users": 50, "sku": 100000, "pos_integrations": None},
    Plan.ENTERPRISE.value: {"stores": None, "users": None, "sku": None, "pos_integrations": None},
}
PLAN_PRICES = {"STANDARD": 59, "PRO": 119, "BUSINESS": 249, "ENTERPRISE": None}
FEATURE_MIN_PLAN = {feature: next(plan for plan in ("STANDARD", "PRO", "BUSINESS", "ENTERPRISE") if feature in PLAN_FEATURES[plan]) for feature in ENTERPRISE}


class PlanService:
    @staticmethod
    def subscription(db: Session, tenant_id: int) -> Subscription:
        row = db.query(Subscription).filter(Subscription.tenant_id == tenant_id).first()
        if row:
            return row
        # Compatibility fallback for a tenant created while the migration is rolling out.
        row = Subscription(tenant_id=tenant_id, plan="PRO", status="ACTIVE")
        db.add(row)
        db.flush()
        return row

    @staticmethod
    def _override(db: Session, tenant_id: int):
        row = db.query(SubscriptionOverride).filter(SubscriptionOverride.tenant_id == tenant_id).first()
        if row and (row.expires_at is None or row.expires_at > datetime.now(timezone.utc)):
            return row
        return None

    @classmethod
    def is_available(cls, subscription: Subscription) -> bool:
        if subscription.status == SubscriptionStatus.TRIAL.value and subscription.trial_ends_at:
            end = subscription.trial_ends_at
            if end.tzinfo is None:
                end = end.replace(tzinfo=timezone.utc)
            return end > datetime.now(timezone.utc)
        return subscription.status == SubscriptionStatus.ACTIVE.value

    @classmethod
    def has_feature(cls, db: Session, tenant_id: int, feature: str) -> bool:
        sub = cls.subscription(db, tenant_id)
        if not cls.is_available(sub):
            return False
        override = cls._override(db, tenant_id)
        if override and feature in (override.feature_overrides or {}):
            return bool(override.feature_overrides[feature])
        return feature in PLAN_FEATURES.get(sub.plan, set())

    @classmethod
    def limits(cls, db: Session, tenant_id: int) -> dict[str, int | None]:
        sub = cls.subscription(db, tenant_id)
        result = dict(PLAN_LIMITS.get(sub.plan, PLAN_LIMITS["STANDARD"]))
        for key, value in (("stores", sub.stores_limit), ("users", sub.users_limit), ("sku", sub.sku_limit)):
            if value is not None:
                result[key] = value
        override = cls._override(db, tenant_id)
        if override:
            for key, attr in (("stores", "stores_max"), ("users", "users_max"), ("sku", "sku_max")):
                value = getattr(override, attr)
                if value is not None:
                    result[key] = value
        return result

    @staticmethod
    def usage(db: Session, tenant_id: int) -> dict[str, int]:
        from app.integrations.models import POSIntegration
        return {
            "stores": db.query(TenantStore).filter(TenantStore.tenant_id == tenant_id, TenantStore.is_active == True).count(),
            "users": db.query(User).filter(User.tenant_id == tenant_id, User.is_active == True).count(),
            "sku": db.query(Product).filter(Product.tenant_id == tenant_id, Product.is_active == True).count(),
            "pos_integrations": db.query(POSIntegration).filter(POSIntegration.tenant_id == tenant_id, POSIntegration.status != "DISABLED").count(),
        }

    @classmethod
    def assert_limit(cls, db: Session, tenant_id: int, resource: str, increment: int = 1):
        limit = cls.limits(db, tenant_id).get(resource)
        used = cls.usage(db, tenant_id).get(resource, 0)
        if limit is not None and used + increment > limit:
            sub = cls.subscription(db, tenant_id)
            raise HTTPException(status_code=403, detail={"error": "LIMIT_REACHED", "resource": resource, "used": used, "max": limit, "plan": sub.plan})


def require_feature(feature: str):
    def dependency(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
        if not PlanService.has_feature(db, user.tenant_id, feature):
            raise HTTPException(status_code=403, detail={"error": "FEATURE_NOT_AVAILABLE", "feature": feature, "required_plan": FEATURE_MIN_PLAN.get(feature, "ENTERPRISE")})
        return user
    return dependency
