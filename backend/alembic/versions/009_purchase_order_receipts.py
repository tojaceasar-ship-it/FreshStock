"""Link deliveries to purchase orders and protect delivery document numbers.

Revision ID: 009
Revises: 008
"""
from alembic import op
import sqlalchemy as sa


revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade():
    from app.core.migration_bootstrap import current_schema_was_bootstrapped
    if current_schema_was_bootstrapped(op.get_bind()): return
    with op.batch_alter_table("deliveries") as batch:
        batch.add_column(sa.Column("purchase_order_id", sa.Integer(), nullable=True))
        batch.create_index("ix_deliveries_purchase_order_id", ["purchase_order_id"])
        batch.create_foreign_key(
            "fk_deliveries_purchase_order_id",
            "purchase_orders",
            ["purchase_order_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_unique_constraint("uq_delivery_tenant_document", ["tenant_id", "document_number"])


def downgrade():
    from app.core.migration_bootstrap import current_schema_was_bootstrapped
    if current_schema_was_bootstrapped(op.get_bind()): return
    with op.batch_alter_table("deliveries") as batch:
        batch.drop_constraint("uq_delivery_tenant_document", type_="unique")
        batch.drop_constraint("fk_deliveries_purchase_order_id", type_="foreignkey")
        batch.drop_index("ix_deliveries_purchase_order_id")
        batch.drop_column("purchase_order_id")
