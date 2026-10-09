"""Full tenant isolation for store data

Revision ID: 004
Revises: 003
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TENANT_TABLES = [
    "categories", "suppliers", "products", "product_suppliers", "batches", "stock",
    "stock_movements", "deliveries", "delivery_items", "purchase_orders",
    "purchase_order_items", "sales", "sale_items", "waste", "promotions",
    "inventory_counts", "inventory_count_items", "alerts", "audit_logs", "settings",
]


def upgrade() -> None:
    from app.core.migration_bootstrap import current_schema_was_bootstrapped
    if current_schema_was_bootstrapped(op.get_bind()): return
    for table in TENANT_TABLES:
        op.add_column(table, sa.Column("tenant_id", sa.Integer(), server_default="1", nullable=False))
        op.create_index(f"ix_{table}_tenant_id", table, ["tenant_id"])

    # Replace global business identifiers with tenant-local identifiers.
    global_indexes = [
        ("categories", "ix_categories_name", ["name"]), ("products", "ix_products_sku", ["sku"]),
        ("products", "ix_products_ean", ["ean"]), ("warehouse_locations", "ix_warehouse_locations_code", ["code"]),
        ("purchase_orders", "ix_purchase_orders_order_number", ["order_number"]), ("sales", "ix_sales_sale_number", ["sale_number"]),
        ("inventory_counts", "ix_inventory_counts_count_number", ["count_number"]), ("settings", "ix_settings_key", ["key"]),
    ]
    for table, index, columns in global_indexes:
        op.drop_index(index, table_name=table)
        op.create_index(index, table, columns, unique=False)
    op.drop_constraint("uq_product_location", "stock", type_="unique")

    op.create_unique_constraint("uq_category_tenant_name", "categories", ["tenant_id", "name"])
    op.create_unique_constraint("uq_product_tenant_sku", "products", ["tenant_id", "sku"])
    op.create_unique_constraint("uq_product_tenant_ean", "products", ["tenant_id", "ean"])
    op.create_unique_constraint("uq_location_tenant_code", "warehouse_locations", ["tenant_id", "code"])
    op.create_unique_constraint("uq_po_tenant_number", "purchase_orders", ["tenant_id", "order_number"])
    op.create_unique_constraint("uq_sale_tenant_number", "sales", ["tenant_id", "sale_number"])
    op.create_unique_constraint("uq_count_tenant_number", "inventory_counts", ["tenant_id", "count_number"])
    op.create_unique_constraint("uq_setting_tenant_key", "settings", ["tenant_id", "key"])
    op.create_unique_constraint("uq_tenant_product_location", "stock", ["tenant_id", "product_id", "location_id"])


def downgrade() -> None:
    from app.core.migration_bootstrap import current_schema_was_bootstrapped
    if current_schema_was_bootstrapped(op.get_bind()): return
    for table, constraint in [
        ("categories", "uq_category_tenant_name"), ("products", "uq_product_tenant_sku"),
        ("products", "uq_product_tenant_ean"), ("warehouse_locations", "uq_location_tenant_code"),
        ("purchase_orders", "uq_po_tenant_number"), ("sales", "uq_sale_tenant_number"),
        ("inventory_counts", "uq_count_tenant_number"), ("settings", "uq_setting_tenant_key"),
        ("stock", "uq_tenant_product_location"),
    ]:
        op.drop_constraint(constraint, table, type_="unique")
    global_indexes = [
        ("categories", "ix_categories_name", ["name"]), ("products", "ix_products_sku", ["sku"]),
        ("products", "ix_products_ean", ["ean"]), ("warehouse_locations", "ix_warehouse_locations_code", ["code"]),
        ("purchase_orders", "ix_purchase_orders_order_number", ["order_number"]), ("sales", "ix_sales_sale_number", ["sale_number"]),
        ("inventory_counts", "ix_inventory_counts_count_number", ["count_number"]), ("settings", "ix_settings_key", ["key"]),
    ]
    for table, index, columns in global_indexes:
        op.drop_index(index, table_name=table)
        op.create_index(index, table, columns, unique=True)
    op.create_unique_constraint("uq_product_location", "stock", ["product_id", "location_id"])
    for table in reversed(TENANT_TABLES):
        op.drop_index(f"ix_{table}_tenant_id", table_name=table)
        op.drop_column(table, "tenant_id")
