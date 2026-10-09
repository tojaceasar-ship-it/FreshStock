"""Scanner telemetry without raw barcode storage

Revision ID: 005
Revises: 004
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from app.core.migration_bootstrap import current_schema_was_bootstrapped
    if current_schema_was_bootstrapped(op.get_bind()): return
    op.create_table(
        "scan_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("device_id", sa.String(64), nullable=False),
        sa.Column("context", sa.String(30), nullable=False),
        sa.Column("outcome", sa.String(30), nullable=False),
        sa.Column("barcode_format", sa.String(30), nullable=True),
        sa.Column("code_length", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("error_reason", sa.String(100), nullable=True),
        sa.Column("platform", sa.String(30), nullable=True),
        sa.Column("user_agent", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    for column in ["tenant_id", "user_id", "device_id", "context", "outcome", "error_reason", "platform", "created_at"]:
        op.create_index(f"ix_scan_events_{column}", "scan_events", [column])
    op.create_index("ix_scan_events_tenant_created", "scan_events", ["tenant_id", "created_at"])
    op.create_index("ix_scan_events_tenant_device", "scan_events", ["tenant_id", "device_id"])


def downgrade() -> None:
    from app.core.migration_bootstrap import current_schema_was_bootstrapped
    if current_schema_was_bootstrapped(op.get_bind()): return
    op.drop_table("scan_events")
