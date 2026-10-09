from sqlalchemy import Column, Integer, String, DateTime, Index
from sqlalchemy.sql import func
from app.core.database import Base


class IdempotencyRecord(Base):
    """Stored response for an Idempotency-Key replay.

    One row per (tenant, key). The request fingerprint binds the key to the
    exact method, path and body, so a reused key with a different payload
    is rejected instead of silently returning a stale response.
    """

    __tablename__ = "idempotency_records"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, nullable=False, index=True)
    user_id = Column(Integer, nullable=False)
    key_hash = Column(String(64), nullable=False)
    request_fingerprint = Column(String(64), nullable=False)
    method = Column(String(10), nullable=False)
    path = Column(String(512), nullable=False)
    response_status = Column(Integer, nullable=False)
    response_body = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)

    __table_args__ = (
        Index("ix_idempotency_tenant_key", "tenant_id", "key_hash"),
    )
