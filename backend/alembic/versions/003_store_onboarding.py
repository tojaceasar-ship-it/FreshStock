"""Store setup wizard

Revision ID: 003
Revises: 002
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from app.core.migration_bootstrap import current_schema_was_bootstrapped
    if current_schema_was_bootstrapped(op.get_bind()): return
    op.add_column("warehouse_locations", sa.Column("tenant_id", sa.Integer(), server_default="1", nullable=False))
    op.create_index("ix_warehouse_locations_tenant_id", "warehouse_locations", ["tenant_id"])
    op.create_table("store_settings",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("tenant_id", sa.Integer(), nullable=False, unique=True),
        sa.Column("business_type", sa.String(50)), sa.Column("store_name", sa.String(255)), sa.Column("company_name", sa.String(255)),
        sa.Column("address", sa.String(500)), sa.Column("vat_number", sa.String(50)), sa.Column("country", sa.String(2), nullable=False, server_default="PL"),
        sa.Column("currency", sa.String(3), nullable=False, server_default="PLN"), sa.Column("timezone", sa.String(100), nullable=False, server_default="Europe/Warsaw"),
        sa.Column("language", sa.String(10), nullable=False, server_default="pl"), sa.Column("store_size", sa.String(50)),
        sa.Column("employee_count", sa.Integer()), sa.Column("approximate_sku_count", sa.Integer()), sa.Column("pos_count", sa.Integer()),
        sa.Column("expiry_rules", sa.JSON(), nullable=False), sa.Column("fefo_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("expiry_tracking", sa.Boolean(), nullable=False, server_default=sa.false()), sa.Column("waste_tracking", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("high_frequency_waste_tracking", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("markdown_suggestions_enabled", sa.Boolean(), nullable=False, server_default=sa.false()), sa.Column("markdown_rules", sa.JSON(), nullable=False),
        sa.Column("delivery_frequency", sa.String(40)), sa.Column("require_expiry_on_receiving", sa.String(40)), sa.Column("batch_tracking", sa.String(20)),
        sa.Column("sales_method", sa.String(40)), sa.Column("selected_pos_provider", sa.String(50)), sa.Column("product_import_method", sa.String(40)),
        sa.Column("dashboard_layout", sa.JSON(), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
    op.create_index("ix_store_settings_tenant_id", "store_settings", ["tenant_id"], unique=True)
    op.create_table("onboarding_progress", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("tenant_id", sa.Integer(), nullable=False, unique=True),
        sa.Column("current_step", sa.Integer(), nullable=False, server_default="1"), sa.Column("completed_steps", sa.JSON(), nullable=False),
        sa.Column("step_data", sa.JSON(), nullable=False), sa.Column("status", sa.String(20), nullable=False, server_default="NOT_STARTED"),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
    op.create_index("ix_onboarding_progress_tenant_id", "onboarding_progress", ["tenant_id"], unique=True)
    op.create_table("business_priorities", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("priority", sa.String(50), nullable=False), sa.UniqueConstraint("tenant_id", "priority", name="uq_business_priority"))
    op.create_index("ix_business_priorities_tenant_id", "business_priorities", ["tenant_id"])
    op.create_table("notification_settings", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("tenant_id", sa.Integer(), nullable=False, unique=True),
        sa.Column("alert_rules", sa.JSON(), nullable=False), sa.Column("channels", sa.JSON(), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
    op.create_index("ix_notification_settings_tenant_id", "notification_settings", ["tenant_id"], unique=True)
    op.create_table("setup_tasks", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("task_key", sa.String(50), nullable=False), sa.Column("label", sa.String(255), nullable=False), sa.Column("status", sa.String(20), nullable=False, server_default="TODO"),
        sa.Column("is_important", sa.Boolean(), nullable=False, server_default=sa.true()), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "task_key", name="uq_setup_task"))
    op.create_index("ix_setup_tasks_tenant_id", "setup_tasks", ["tenant_id"])


def downgrade() -> None:
    from app.core.migration_bootstrap import current_schema_was_bootstrapped
    if current_schema_was_bootstrapped(op.get_bind()): return
    for table in ["setup_tasks", "notification_settings", "business_priorities", "onboarding_progress", "store_settings"]:
        op.drop_table(table)
    op.drop_index("ix_warehouse_locations_tenant_id", table_name="warehouse_locations")
    op.drop_column("warehouse_locations", "tenant_id")
