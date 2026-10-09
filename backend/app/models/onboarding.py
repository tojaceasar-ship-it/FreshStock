import enum

from sqlalchemy import Boolean, Column, DateTime, Integer, JSON, String, UniqueConstraint
from sqlalchemy.sql import func

from app.core.database import Base


class OnboardingStatus(str, enum.Enum):
    NOT_STARTED = "NOT_STARTED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"


class StoreSettings(Base):
    __tablename__ = "store_settings"
    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, nullable=False, unique=True, index=True)
    business_type = Column(String(50), nullable=True)
    store_name = Column(String(255), nullable=True)
    company_name = Column(String(255), nullable=True)
    address = Column(String(500), nullable=True)
    vat_number = Column(String(50), nullable=True)
    country = Column(String(2), nullable=False, default="PL")
    currency = Column(String(3), nullable=False, default="PLN")
    timezone = Column(String(100), nullable=False, default="Europe/Warsaw")
    language = Column(String(10), nullable=False, default="pl")
    store_size = Column(String(50), nullable=True)
    employee_count = Column(Integer, nullable=True)
    approximate_sku_count = Column(Integer, nullable=True)
    pos_count = Column(Integer, nullable=True)
    expiry_rules = Column(JSON, nullable=False, default=list)
    fefo_enabled = Column(Boolean, nullable=False, default=False)
    expiry_tracking = Column(Boolean, nullable=False, default=False)
    waste_tracking = Column(Boolean, nullable=False, default=True)
    high_frequency_waste_tracking = Column(Boolean, nullable=False, default=False)
    markdown_suggestions_enabled = Column(Boolean, nullable=False, default=False)
    markdown_rules = Column(JSON, nullable=False, default=list)
    delivery_frequency = Column(String(40), nullable=True)
    require_expiry_on_receiving = Column(String(40), nullable=True)
    batch_tracking = Column(String(20), nullable=True)
    sales_method = Column(String(40), nullable=True)
    selected_pos_provider = Column(String(50), nullable=True)
    product_import_method = Column(String(40), nullable=True)
    dashboard_layout = Column(JSON, nullable=False, default=list)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class OnboardingProgress(Base):
    __tablename__ = "onboarding_progress"
    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, nullable=False, unique=True, index=True)
    current_step = Column(Integer, nullable=False, default=1)
    completed_steps = Column(JSON, nullable=False, default=list)
    step_data = Column(JSON, nullable=False, default=dict)
    status = Column(String(20), nullable=False, default=OnboardingStatus.NOT_STARTED.value)
    started_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class BusinessPriority(Base):
    __tablename__ = "business_priorities"
    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, nullable=False, index=True)
    priority = Column(String(50), nullable=False)
    __table_args__ = (UniqueConstraint("tenant_id", "priority", name="uq_business_priority"),)


class NotificationSettings(Base):
    __tablename__ = "notification_settings"
    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, nullable=False, unique=True, index=True)
    alert_rules = Column(JSON, nullable=False, default=dict)
    channels = Column(JSON, nullable=False, default=list)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class SetupTask(Base):
    __tablename__ = "setup_tasks"
    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, nullable=False, index=True)
    task_key = Column(String(50), nullable=False)
    label = Column(String(255), nullable=False)
    status = Column(String(20), nullable=False, default="TODO")
    is_important = Column(Boolean, nullable=False, default=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    __table_args__ = (UniqueConstraint("tenant_id", "task_key", name="uq_setup_task"),)
