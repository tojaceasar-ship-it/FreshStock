"""Store inventory quantities as fixed precision decimals.

Revision ID: 011
Revises: 010

This migration is intentionally not executed by deployment code. Take and
verify a database backup before applying it to any production database.
"""
from alembic import op
import sqlalchemy as sa


revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


COLUMNS = {
    "products": ("min_stock", "target_stock", "safety_stock"),
    "batches": ("quantity_received", "quantity_available"),
    "stock": ("quantity",),
    "stock_movements": ("quantity",),
    "delivery_items": ("quantity_ordered", "quantity_received"),
    "purchase_order_items": ("quantity", "quantity_received"),
    "sale_items": ("quantity",),
    "waste": ("quantity",),
    "inventory_count_items": ("system_quantity", "counted_quantity", "difference"),
}


def upgrade():
    from app.core.migration_bootstrap import current_schema_was_bootstrapped
    if current_schema_was_bootstrapped(op.get_bind()): return
    decimal_type = sa.Numeric(14, 3)
    for table, columns in COLUMNS.items():
        for column in columns:
            op.alter_column(
                table,
                column,
                existing_type=sa.Integer(),
                type_=decimal_type,
                postgresql_using=f"{column}::numeric(14,3)",
                existing_nullable=column not in {
                    "quantity_received", "quantity_available", "quantity",
                    "counted_quantity",
                },
            )


def downgrade():
    from app.core.migration_bootstrap import current_schema_was_bootstrapped
    if current_schema_was_bootstrapped(op.get_bind()): return
    # Downgrade is deliberately explicit and lossy. Production rollback should
    # restore the verified pre-migration backup instead of rounding live data.
    for table, columns in reversed(tuple(COLUMNS.items())):
        for column in columns:
            op.alter_column(
                table,
                column,
                existing_type=sa.Numeric(14, 3),
                type_=sa.Integer(),
                postgresql_using=f"round({column})::integer",
                existing_nullable=column not in {
                    "quantity_received", "quantity_available", "quantity",
                    "counted_quantity",
                },
            )
