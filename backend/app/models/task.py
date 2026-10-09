from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, nullable=False, index=True)
    created_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    assigned_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    assigned_role = Column(String(30), nullable=True, index=True)
    source = Column(String(30), nullable=False, default="OWNER", server_default="OWNER", index=True)
    system_key = Column(String(180), nullable=True, index=True)
    task_type = Column(String(40), nullable=False, default="GENERAL", server_default="GENERAL", index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    priority = Column(String(20), nullable=False, default="MEDIUM", server_default="MEDIUM", index=True)
    status = Column(String(30), nullable=False, default="TODO", server_default="TODO", index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="SET NULL"), nullable=True, index=True)
    batch_id = Column(Integer, ForeignKey("batches.id", ondelete="SET NULL"), nullable=True, index=True)
    location_id = Column(Integer, ForeignKey("warehouse_locations.id", ondelete="SET NULL"), nullable=True, index=True)
    quantity = Column(Numeric(12, 3), nullable=True)
    due_at = Column(DateTime(timezone=True), nullable=True, index=True)
    requires_photo = Column(Boolean, nullable=False, default=False, server_default="false")
    requires_scan = Column(Boolean, nullable=False, default=False, server_default="false")
    requires_comment = Column(Boolean, nullable=False, default=False, server_default="false")
    recurrence_rule = Column(String(20), nullable=True)
    recurrence_days = Column(JSON, nullable=False, default=list)
    recurrence_parent_id = Column(Integer, ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True, index=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (UniqueConstraint("tenant_id", "system_key", name="uq_task_tenant_system_key"),)

    creator = relationship("User", foreign_keys=[created_by_user_id])
    assignee = relationship("User", foreign_keys=[assigned_user_id])
    product = relationship("Product")
    batch = relationship("Batch")
    location = relationship("WarehouseLocation")
    comments = relationship("TaskComment", cascade="all, delete-orphan", back_populates="task", order_by="TaskComment.created_at")
    attachments = relationship("TaskAttachment", cascade="all, delete-orphan", back_populates="task", order_by="TaskAttachment.created_at")
    checklist_items = relationship("TaskChecklistItem", cascade="all, delete-orphan", back_populates="task", order_by="TaskChecklistItem.position")
    activity = relationship("TaskActivityLog", cascade="all, delete-orphan", back_populates="task", order_by="TaskActivityLog.created_at")


class TaskComment(Base):
    __tablename__ = "task_comments"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, nullable=False, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    body = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    task = relationship("Task", back_populates="comments")
    user = relationship("User")


class TaskAttachment(Base):
    __tablename__ = "task_attachments"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, nullable=False, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    uploaded_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    object_key = Column(String(700), nullable=False, unique=True)
    file_name = Column(String(255), nullable=False)
    content_type = Column(String(100), nullable=False)
    size_bytes = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    task = relationship("Task", back_populates="attachments")
    uploader = relationship("User")


class TaskChecklistItem(Base):
    __tablename__ = "task_checklist_items"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, nullable=False, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    text = Column(String(500), nullable=False)
    position = Column(Integer, nullable=False, default=0)
    is_completed = Column(Boolean, nullable=False, default=False, server_default="false")
    completed_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    task = relationship("Task", back_populates="checklist_items")
    completed_by = relationship("User")
    __table_args__ = (UniqueConstraint("task_id", "position", name="uq_task_checklist_position"),)


class TaskActivityLog(Base):
    __tablename__ = "task_activity_log"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, nullable=False, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    event = Column(String(50), nullable=False, index=True)
    details = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    task = relationship("Task", back_populates="activity")
    user = relationship("User")
