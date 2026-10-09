"""initial

Revision ID: 001
Revises: 
Create Date: 2026-09-23

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    bind = op.get_bind()
    if set(sa.inspect(bind).get_table_names()) <= {"alembic_version"}:
        import app.models  # noqa: F401
        import app.integrations.models  # noqa: F401
        from app.core.database import Base
        Base.metadata.create_all(bind)
        op.create_table("_freshstock_schema_bootstrap", sa.Column("id", sa.Integer(), primary_key=True))

def downgrade() -> None:
    bind = op.get_bind()
    if sa.inspect(bind).has_table("_freshstock_schema_bootstrap"):
        import app.models  # noqa: F401
        import app.integrations.models  # noqa: F401
        from app.core.database import Base
        Base.metadata.drop_all(bind)
        op.drop_table("_freshstock_schema_bootstrap")
