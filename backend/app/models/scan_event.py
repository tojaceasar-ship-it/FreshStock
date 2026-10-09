from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.sql import func

from app.core.database import Base


class ScanEvent(Base):
    __tablename__ = "scan_events"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    device_id = Column(String(64), nullable=False, index=True)
    context = Column(String(30), nullable=False, index=True)
    outcome = Column(String(30), nullable=False, index=True)
    barcode_format = Column(String(30), nullable=True)
    code_length = Column(Integer, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    error_reason = Column(String(100), nullable=True, index=True)
    platform = Column(String(30), nullable=True, index=True)
    user_agent = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    __table_args__ = (
        Index("ix_scan_events_tenant_created", "tenant_id", "created_at"),
        Index("ix_scan_events_tenant_device", "tenant_id", "device_id"),
    )
