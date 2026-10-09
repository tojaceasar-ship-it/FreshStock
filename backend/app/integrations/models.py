from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, JSON, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class POSIntegration(Base):
    __tablename__ = "pos_integrations"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, nullable=False, index=True)
    provider = Column(String(50), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    status = Column(String(30), nullable=False, default="DISABLED", index=True)
    external_merchant_id = Column(String(255), nullable=True)
    external_location_id = Column(String(255), nullable=True)
    credentials_encrypted = Column(Text, nullable=True)
    settings = Column(JSON, nullable=True)
    sync_mode = Column(String(30), nullable=False, default="CSV")
    last_sync_at = Column(DateTime(timezone=True), nullable=True)
    last_success_at = Column(DateTime(timezone=True), nullable=True)
    last_error_at = Column(DateTime(timezone=True), nullable=True)
    sync_lock_until = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    mappings = relationship("POSProductMapping", back_populates="integration", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_pos_integrations_tenant_provider", "tenant_id", "provider"),
    )


class POSProductMapping(Base):
    __tablename__ = "pos_product_mappings"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, nullable=False, index=True)
    integration_id = Column(Integer, ForeignKey("pos_integrations.id", ondelete="CASCADE"), nullable=False, index=True)
    provider = Column(String(50), nullable=False)
    external_product_id = Column(String(255), nullable=False)
    freshstock_product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    ean = Column(String(50), nullable=True, index=True)
    sku = Column(String(100), nullable=True, index=True)
    mapping_method = Column(String(30), nullable=False)
    confidence = Column(Numeric(5, 4), nullable=False, default=1)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    integration = relationship("POSIntegration", back_populates="mappings")
    product = relationship("Product")

    __table_args__ = (
        UniqueConstraint("integration_id", "external_product_id", name="uq_pos_mapping_external_product"),
        Index("ix_pos_mapping_tenant_integration", "tenant_id", "integration_id"),
    )


class IntegrationEvent(Base):
    __tablename__ = "integration_events"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, nullable=False, index=True)
    integration_id = Column(Integer, ForeignKey("pos_integrations.id", ondelete="CASCADE"), nullable=False, index=True)
    provider = Column(String(50), nullable=False)
    external_event_id = Column(String(255), nullable=False)
    external_transaction_id = Column(String(255), nullable=True, index=True)
    event_type = Column(String(40), nullable=False, index=True)
    payload_hash = Column(String(64), nullable=False)
    payload = Column(JSON, nullable=True)
    status = Column(String(30), nullable=False, default="RECEIVED", index=True)
    sale_id = Column(Integer, ForeignKey("sales.id", ondelete="SET NULL"), nullable=True)
    received_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    processed_at = Column(DateTime(timezone=True), nullable=True)
    error_message = Column(Text, nullable=True)

    integration = relationship("POSIntegration")
    sale = relationship("Sale")

    __table_args__ = (
        UniqueConstraint("integration_id", "external_event_id", name="uq_integration_event_external"),
        Index("ix_integration_event_tenant_integration", "tenant_id", "integration_id"),
    )


class IntegrationSyncLog(Base):
    __tablename__ = "integration_sync_logs"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, nullable=False, index=True)
    integration_id = Column(Integer, ForeignKey("pos_integrations.id", ondelete="CASCADE"), nullable=False, index=True)
    started_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    sync_type = Column(String(50), nullable=False)
    records_received = Column(Integer, nullable=False, default=0)
    records_processed = Column(Integer, nullable=False, default=0)
    records_failed = Column(Integer, nullable=False, default=0)
    status = Column(String(30), nullable=False, default="RUNNING")
    error_message = Column(Text, nullable=True)


class IntegrationError(Base):
    __tablename__ = "integration_errors"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, nullable=False, index=True)
    integration_id = Column(Integer, ForeignKey("pos_integrations.id", ondelete="CASCADE"), nullable=False, index=True)
    event_id = Column(Integer, ForeignKey("integration_events.id", ondelete="SET NULL"), nullable=True, index=True)
    error_type = Column(String(50), nullable=False, index=True)
    message = Column(Text, nullable=False)
    payload = Column(JSON, nullable=True)
    resolved = Column(Boolean, nullable=False, default=False, index=True)
    resolved_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class CSVMappingTemplate(Base):
    __tablename__ = "integration_csv_templates"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, nullable=False, index=True)
    integration_id = Column(Integer, ForeignKey("pos_integrations.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    delimiter = Column(String(5), nullable=False, default=",")
    date_format = Column(String(100), nullable=True)
    column_mapping = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (UniqueConstraint("integration_id", "name", name="uq_csv_template_name"),)


class PendingReturn(Base):
    __tablename__ = "integration_pending_returns"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, nullable=False, index=True)
    integration_id = Column(Integer, ForeignKey("pos_integrations.id", ondelete="CASCADE"), nullable=False, index=True)
    event_id = Column(Integer, ForeignKey("integration_events.id", ondelete="CASCADE"), nullable=False, unique=True)
    original_sale_id = Column(Integer, ForeignKey("sales.id", ondelete="SET NULL"), nullable=True)
    status = Column(String(30), nullable=False, default="RETURN_PENDING", index=True)
    items = Column(JSON, nullable=False)
    resolved_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class POSBridge(Base):
    __tablename__ = "pos_bridges"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, nullable=False, index=True)
    integration_id = Column(Integer, ForeignKey("pos_integrations.id", ondelete="CASCADE"), nullable=False, index=True)
    bridge_id = Column(String(100), nullable=False, unique=True, index=True)
    store_id = Column(String(100), nullable=False)
    secret_encrypted = Column(Text, nullable=False)
    last_seen = Column(DateTime(timezone=True), nullable=True)
    version = Column(String(50), nullable=True)
    status = Column(String(30), nullable=False, default="ACTIVE")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
