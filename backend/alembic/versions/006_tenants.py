"""Add first-class tenants for independent store registration.

Revision ID: 006
Revises: 005
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from app.core.migration_bootstrap import current_schema_was_bootstrapped
    if current_schema_was_bootstrapped(op.get_bind()): return
    op.create_table(
        "tenants",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.execute(sa.text("""
        INSERT INTO tenants (id, name)
        SELECT u.tenant_id, COALESCE(MAX(NULLIF(s.store_name, '')), 'Sklep ' || CAST(u.tenant_id AS VARCHAR))
        FROM (SELECT DISTINCT tenant_id FROM users) AS u
        LEFT JOIN store_settings AS s ON s.tenant_id = u.tenant_id
        GROUP BY u.tenant_id
    """))
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(sa.text("""
            SELECT setval(
                pg_get_serial_sequence('tenants', 'id'),
                COALESCE((SELECT MAX(id) FROM tenants), 1),
                EXISTS (SELECT 1 FROM tenants)
            )
        """))


def downgrade() -> None:
    from app.core.migration_bootstrap import current_schema_was_bootstrapped
    if current_schema_was_bootstrapped(op.get_bind()): return
    op.drop_table("tenants")
