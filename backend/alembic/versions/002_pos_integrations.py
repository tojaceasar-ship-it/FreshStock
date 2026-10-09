"""POS Integration Gateway

Revision ID: 002
Revises: 001
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from app.core.migration_bootstrap import current_schema_was_bootstrapped
    if current_schema_was_bootstrapped(op.get_bind()): return
    op.add_column("users", sa.Column("tenant_id", sa.Integer(), server_default="1", nullable=False))
    op.create_index("ix_users_tenant_id", "users", ["tenant_id"])

    op.execute("ALTER TYPE movementtype ADD VALUE IF NOT EXISTS 'SALE_REVERSAL'")
    op.execute("ALTER TYPE alerttype ADD VALUE IF NOT EXISTS 'INVENTORY_DESYNC'")

    op.create_table(
        "pos_integrations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="DISABLED"),
        sa.Column("external_merchant_id", sa.String(255)),
        sa.Column("external_location_id", sa.String(255)),
        sa.Column("credentials_encrypted", sa.Text()),
        sa.Column("settings", sa.JSON()),
        sa.Column("sync_mode", sa.String(30), nullable=False, server_default="CSV"),
        sa.Column("last_sync_at", sa.DateTime(timezone=True)),
        sa.Column("last_success_at", sa.DateTime(timezone=True)),
        sa.Column("last_error_at", sa.DateTime(timezone=True)),
        sa.Column("sync_lock_until", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_pos_integrations_tenant_id", "pos_integrations", ["tenant_id"])
    op.create_index("ix_pos_integrations_provider", "pos_integrations", ["provider"])
    op.create_index("ix_pos_integrations_status", "pos_integrations", ["status"])
    op.create_index("ix_pos_integrations_tenant_provider", "pos_integrations", ["tenant_id", "provider"])

    op.create_table(
        "pos_product_mappings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("integration_id", sa.Integer(), sa.ForeignKey("pos_integrations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("external_product_id", sa.String(255), nullable=False),
        sa.Column("freshstock_product_id", sa.Integer(), sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ean", sa.String(50)),
        sa.Column("sku", sa.String(100)),
        sa.Column("mapping_method", sa.String(30), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("integration_id", "external_product_id", name="uq_pos_mapping_external_product"),
    )
    for name, cols in [
        ("ix_pos_product_mappings_tenant_id", ["tenant_id"]), ("ix_pos_product_mappings_integration_id", ["integration_id"]),
        ("ix_pos_product_mappings_freshstock_product_id", ["freshstock_product_id"]), ("ix_pos_product_mappings_ean", ["ean"]),
        ("ix_pos_product_mappings_sku", ["sku"]), ("ix_pos_mapping_tenant_integration", ["tenant_id", "integration_id"]),
    ]:
        op.create_index(name, "pos_product_mappings", cols)

    op.create_table(
        "integration_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("integration_id", sa.Integer(), sa.ForeignKey("pos_integrations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("external_event_id", sa.String(255), nullable=False),
        sa.Column("external_transaction_id", sa.String(255)),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON()),
        sa.Column("status", sa.String(30), nullable=False, server_default="RECEIVED"),
        sa.Column("sale_id", sa.Integer(), sa.ForeignKey("sales.id", ondelete="SET NULL")),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
        sa.Column("error_message", sa.Text()),
        sa.UniqueConstraint("integration_id", "external_event_id", name="uq_integration_event_external"),
    )
    for name, cols in [
        ("ix_integration_events_tenant_id", ["tenant_id"]), ("ix_integration_events_integration_id", ["integration_id"]),
        ("ix_integration_events_external_transaction_id", ["external_transaction_id"]), ("ix_integration_events_event_type", ["event_type"]),
        ("ix_integration_events_status", ["status"]), ("ix_integration_event_tenant_integration", ["tenant_id", "integration_id"]),
    ]:
        op.create_index(name, "integration_events", cols)

    op.create_table(
        "integration_sync_logs",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("integration_id", sa.Integer(), sa.ForeignKey("pos_integrations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("sync_type", sa.String(50), nullable=False), sa.Column("records_received", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_processed", sa.Integer(), nullable=False, server_default="0"), sa.Column("records_failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(30), nullable=False, server_default="RUNNING"), sa.Column("error_message", sa.Text()),
    )
    op.create_index("ix_integration_sync_logs_tenant_id", "integration_sync_logs", ["tenant_id"])
    op.create_index("ix_integration_sync_logs_integration_id", "integration_sync_logs", ["integration_id"])

    op.create_table(
        "integration_errors",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("integration_id", sa.Integer(), sa.ForeignKey("pos_integrations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_id", sa.Integer(), sa.ForeignKey("integration_events.id", ondelete="SET NULL")),
        sa.Column("error_type", sa.String(50), nullable=False), sa.Column("message", sa.Text(), nullable=False), sa.Column("payload", sa.JSON()),
        sa.Column("resolved", sa.Boolean(), nullable=False, server_default=sa.false()), sa.Column("resolved_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("resolved_at", sa.DateTime(timezone=True)), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    for name, cols in [("ix_integration_errors_tenant_id", ["tenant_id"]), ("ix_integration_errors_integration_id", ["integration_id"]), ("ix_integration_errors_event_id", ["event_id"]), ("ix_integration_errors_error_type", ["error_type"]), ("ix_integration_errors_resolved", ["resolved"])]:
        op.create_index(name, "integration_errors", cols)

    op.create_table(
        "integration_csv_templates",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("integration_id", sa.Integer(), sa.ForeignKey("pos_integrations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False), sa.Column("delimiter", sa.String(5), nullable=False, server_default=","),
        sa.Column("date_format", sa.String(100)), sa.Column("column_mapping", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("integration_id", "name", name="uq_csv_template_name"),
    )
    op.create_index("ix_integration_csv_templates_tenant_id", "integration_csv_templates", ["tenant_id"])
    op.create_index("ix_integration_csv_templates_integration_id", "integration_csv_templates", ["integration_id"])

    op.create_table(
        "integration_pending_returns",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("integration_id", sa.Integer(), sa.ForeignKey("pos_integrations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_id", sa.Integer(), sa.ForeignKey("integration_events.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("original_sale_id", sa.Integer(), sa.ForeignKey("sales.id", ondelete="SET NULL")),
        sa.Column("status", sa.String(30), nullable=False, server_default="RETURN_PENDING"), sa.Column("items", sa.JSON(), nullable=False),
        sa.Column("resolved_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")), sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_integration_pending_returns_tenant_id", "integration_pending_returns", ["tenant_id"])
    op.create_index("ix_integration_pending_returns_integration_id", "integration_pending_returns", ["integration_id"])
    op.create_index("ix_integration_pending_returns_status", "integration_pending_returns", ["status"])

    op.create_table(
        "pos_bridges",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("integration_id", sa.Integer(), sa.ForeignKey("pos_integrations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("bridge_id", sa.String(100), nullable=False, unique=True), sa.Column("store_id", sa.String(100), nullable=False),
        sa.Column("secret_encrypted", sa.Text(), nullable=False), sa.Column("last_seen", sa.DateTime(timezone=True)),
        sa.Column("version", sa.String(50)), sa.Column("status", sa.String(30), nullable=False, server_default="ACTIVE"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_pos_bridges_tenant_id", "pos_bridges", ["tenant_id"])
    op.create_index("ix_pos_bridges_integration_id", "pos_bridges", ["integration_id"])
    op.create_index("ix_pos_bridges_bridge_id", "pos_bridges", ["bridge_id"])


def downgrade() -> None:
    from app.core.migration_bootstrap import current_schema_was_bootstrapped
    if current_schema_was_bootstrapped(op.get_bind()): return
    for table in ["pos_bridges", "integration_pending_returns", "integration_csv_templates", "integration_errors", "integration_sync_logs", "integration_events", "pos_product_mappings", "pos_integrations"]:
        op.drop_table(table)
    op.drop_index("ix_users_tenant_id", table_name="users")
    op.drop_column("users", "tenant_id")
