"""Add SaaS subscriptions, entitlements overrides, plan history and tenant stores.

Revision ID: 010
Revises: 009
"""
from alembic import op
import sqlalchemy as sa

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade():
    from app.core.migration_bootstrap import current_schema_was_bootstrapped
    if current_schema_was_bootstrapped(op.get_bind()): return
    op.create_table("subscriptions",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("plan", sa.String(20), nullable=False, server_default="PRO"), sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.Column("billing_cycle", sa.String(20), nullable=False, server_default="MONTHLY"), sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("trial_ends_at", sa.DateTime(timezone=True)), sa.Column("current_period_start", sa.DateTime(timezone=True)), sa.Column("current_period_end", sa.DateTime(timezone=True)),
        sa.Column("cancel_at_period_end", sa.Boolean(), nullable=False, server_default=sa.false()), sa.Column("stores_limit", sa.Integer()), sa.Column("users_limit", sa.Integer()), sa.Column("sku_limit", sa.Integer()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"), sa.UniqueConstraint("tenant_id"))
    op.create_index("ix_subscriptions_tenant_id", "subscriptions", ["tenant_id"], unique=True)
    op.create_table("subscription_overrides",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("tenant_id", sa.Integer(), nullable=False), sa.Column("stores_max", sa.Integer()), sa.Column("users_max", sa.Integer()), sa.Column("sku_max", sa.Integer()),
        sa.Column("feature_overrides", sa.JSON(), nullable=False, server_default="{}"), sa.Column("expires_at", sa.DateTime(timezone=True)), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"), sa.UniqueConstraint("tenant_id"))
    op.create_index("ix_subscription_overrides_tenant_id", "subscription_overrides", ["tenant_id"], unique=True)
    op.create_table("subscription_events",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("tenant_id", sa.Integer(), nullable=False), sa.Column("old_plan", sa.String(20)), sa.Column("new_plan", sa.String(20)), sa.Column("event_type", sa.String(40), nullable=False), sa.Column("created_by", sa.Integer()), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"), sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"))
    op.create_index("ix_subscription_events_tenant_id", "subscription_events", ["tenant_id"])
    op.create_index("ix_subscription_events_created_at", "subscription_events", ["created_at"])
    op.create_table("tenant_stores",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("tenant_id", sa.Integer(), nullable=False), sa.Column("name", sa.String(255), nullable=False), sa.Column("code", sa.String(50), nullable=False), sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"), sa.UniqueConstraint("tenant_id", "code", name="uq_tenant_store_code"))
    op.create_index("ix_tenant_stores_tenant_id", "tenant_stores", ["tenant_id"])
    # Preserve all current production capabilities. New registrations use an explicit 14-day PRO trial.
    op.execute("INSERT INTO subscriptions (tenant_id, plan, status) SELECT id, 'PRO', 'ACTIVE' FROM tenants WHERE id NOT IN (SELECT tenant_id FROM subscriptions)")
    op.execute("INSERT INTO tenant_stores (tenant_id, name, code) SELECT id, name, 'MAIN' FROM tenants WHERE id NOT IN (SELECT tenant_id FROM tenant_stores)")


def downgrade():
    from app.core.migration_bootstrap import current_schema_was_bootstrapped
    if current_schema_was_bootstrapped(op.get_bind()): return
    op.drop_table("tenant_stores")
    op.drop_table("subscription_events")
    op.drop_table("subscription_overrides")
    op.drop_table("subscriptions")
