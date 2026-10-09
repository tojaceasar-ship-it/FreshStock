"""Helpers for installing the recovered pre-Alembic schema."""
import sqlalchemy as sa


def current_schema_was_bootstrapped(bind) -> bool:
    return sa.inspect(bind).has_table("_freshstock_schema_bootstrap")
