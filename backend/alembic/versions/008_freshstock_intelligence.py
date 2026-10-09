"""Add FreshStock Today idempotency and auditable markdown savings.

Revision ID: 008
Revises: 007
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from app.core.migration_bootstrap import current_schema_was_bootstrapped
    if current_schema_was_bootstrapped(op.get_bind()): return
    op.add_column("tasks", sa.Column("system_key", sa.String(180), nullable=True))
    op.create_index("ix_tasks_system_key", "tasks", ["system_key"])
    op.create_unique_constraint("uq_task_tenant_system_key", "tasks", ["tenant_id", "system_key"])

    op.add_column("promotions", sa.Column("strategy", sa.String(40), nullable=False, server_default="MANUAL"))
    op.add_column("promotions", sa.Column("recommendation_data", sa.JSON(), nullable=True))
    op.create_index("ix_promotions_strategy", "promotions", ["strategy"])

    op.add_column("sale_items", sa.Column("promotion_id", sa.Integer(), nullable=True))
    op.add_column("sale_items", sa.Column("regular_unit_price", sa.Numeric(10, 2), nullable=True))
    op.add_column("sale_items", sa.Column("markdown_discount_value", sa.Numeric(12, 2), nullable=False, server_default="0"))
    op.add_column("sale_items", sa.Column("recovered_revenue", sa.Numeric(12, 2), nullable=False, server_default="0"))
    op.add_column("sale_items", sa.Column("protected_cost", sa.Numeric(12, 2), nullable=False, server_default="0"))
    op.create_foreign_key("fk_sale_items_promotion", "sale_items", "promotions", ["promotion_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_sale_items_promotion_id", "sale_items", ["promotion_id"])


def downgrade() -> None:
    from app.core.migration_bootstrap import current_schema_was_bootstrapped
    if current_schema_was_bootstrapped(op.get_bind()): return
    op.drop_index("ix_sale_items_promotion_id", table_name="sale_items")
    op.drop_constraint("fk_sale_items_promotion", "sale_items", type_="foreignkey")
    for column in ["protected_cost", "recovered_revenue", "markdown_discount_value", "regular_unit_price", "promotion_id"]:
        op.drop_column("sale_items", column)
    op.drop_index("ix_promotions_strategy", table_name="promotions")
    op.drop_column("promotions", "recommendation_data")
    op.drop_column("promotions", "strategy")
    op.drop_constraint("uq_task_tenant_system_key", "tasks", type_="unique")
    op.drop_index("ix_tasks_system_key", table_name="tasks")
    op.drop_column("tasks", "system_key")
