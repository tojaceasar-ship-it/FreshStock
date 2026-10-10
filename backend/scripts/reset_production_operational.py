"""Backup and clear FreshStock operational data while retaining accounts/config."""
from __future__ import annotations

import argparse
import json
import os
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlsplit, urlunsplit

from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text


KEEP_TABLES = {
    "alembic_version",
    "tenants",
    "users",
    "subscriptions",
    "subscription_overrides",
    "subscription_events",
    "tenant_stores",
    "store_settings",
    "onboarding_progress",
    "business_priorities",
    "notification_settings",
    "setup_tasks",
    "settings",
}


def json_value(value):
    if isinstance(value, (datetime, date, Decimal)):
        return str(value)
    if isinstance(value, bytes):
        return {"__bytes_hex__": value.hex()}
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--list-admins", action="store_true")
    parser.add_argument("--all-data", action="store_true", help="Retain only the migration version table")
    args = parser.parse_args()
    load_dotenv(".env.production.local")
    database_url = os.environ.get("DATABASE_URL", "")
    parsed = urlparse(database_url.replace("postgresql+pg8000://", "postgresql://", 1))
    if not parsed.hostname or not parsed.hostname.endswith("neon.tech"):
        raise SystemExit("REFUSED: DATABASE_URL is not an expected Neon production host")
    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+pg8000://", 1)
    parts = urlsplit(database_url)
    query = [(key, value) for key, value in parse_qsl(parts.query) if key not in {"sslmode", "channel_binding"}]
    database_url = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))

    engine = create_engine(database_url, pool_pre_ping=True, connect_args={"ssl_context": True})
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    missing = {"tenants", "users"} - tables
    if missing:
        raise SystemExit(f"REFUSED: identity tables missing: {sorted(missing)}")
    keep = ({"alembic_version"} if args.all_data else KEEP_TABLES) & tables
    operational = sorted(tables - keep)

    unsafe_dependencies = []
    for table in keep:
        for fk in inspector.get_foreign_keys(table):
            if fk.get("referred_table") in operational:
                unsafe_dependencies.append(f"{table} -> {fk['referred_table']}")
    if unsafe_dependencies:
        raise SystemExit(f"REFUSED: retained tables depend on operational tables: {unsafe_dependencies}")

    with engine.connect() as connection:
        counts = {
            table: connection.execute(text(f'SELECT COUNT(*) FROM "{table}"')).scalar_one()
            for table in sorted(tables)
        }
        print(json.dumps({"keep": sorted(keep), "operational": operational, "counts": counts}, indent=2))
        if args.list_admins:
            owners = connection.execute(text(
                'SELECT id, tenant_id, username, email, role, is_active, created_at '
                'FROM users WHERE role = \'OWNER\' ORDER BY created_at, id'
            )).mappings().all()
            print(json.dumps({"owners": [dict(row) for row in owners]}, default=str, indent=2))
        if not args.execute:
            return
        expected_confirmation = "FRESHSTOCK_ALL_DATA" if args.all_data else "FRESHSTOCK_OPERATIONAL_ONLY"
        if os.environ.get("ALLOW_PRODUCTION_RESET") != expected_confirmation:
            raise SystemExit(f"REFUSED: set ALLOW_PRODUCTION_RESET={expected_confirmation}")

        backup_dir = Path(".maintenance-backups")
        backup_dir.mkdir(exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup_path = backup_dir / f"freshstock-production-before-reset-{stamp}.json"
        backup = {"created_at": stamp, "host": parsed.hostname, "tables": {}}
        for table in sorted(tables):
            rows = connection.execute(text(f'SELECT * FROM "{table}"')).mappings().all()
            backup["tables"][table] = [
                {key: json_value(value) for key, value in row.items()} for row in rows
            ]
        backup_path.write_text(json.dumps(backup, ensure_ascii=False, indent=2), encoding="utf-8")

        quoted = ", ".join(f'"{table}"' for table in operational)
        connection.commit()
        with connection.begin():
            if quoted:
                connection.execute(text(f"TRUNCATE TABLE {quoted} RESTART IDENTITY"))

        remaining = {
            table: connection.execute(text(f'SELECT COUNT(*) FROM "{table}"')).scalar_one()
            for table in operational
        }
        if any(remaining.values()):
            raise SystemExit(f"RESET FAILED: operational rows remain: {remaining}")
        retained = {
            table: connection.execute(text(f'SELECT COUNT(*) FROM "{table}"')).scalar_one()
            for table in sorted(keep)
        }
        print(json.dumps({"result": "RESET_OK", "backup": str(backup_path), "retained": retained}, indent=2))


if __name__ == "__main__":
    main()
