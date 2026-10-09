"""Bezpieczna aktualizacja lokalnej bazy SQLite FreshStock.

Migracje produkcyjne są zoptymalizowane dla PostgreSQL. Ten skrypt zachowuje
lokalne dane demonstracyjne, dodaje kolumny izolacji tenantów i tworzy tabele,
które pojawiły się w późniejszych wersjach aplikacji.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, inspect, text

from app.core.database import Base
import app.models  # noqa: F401


def _backup_database(source: Path) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = source.with_name(f"{source.name}.backup-{timestamp}")
    with sqlite3.connect(source) as source_db, sqlite3.connect(target) as target_db:
        source_db.backup(target_db)
    return target


def upgrade_sqlite(database: Path, *, create_backup: bool = True) -> dict[str, object]:
    database = database.resolve()
    if not database.is_file():
        raise FileNotFoundError(f"Nie znaleziono bazy SQLite: {database}")

    backup = _backup_database(database) if create_backup else None
    engine = create_engine(f"sqlite:///{database.as_posix()}")
    added_columns: list[str] = []

    try:
        inspector = inspect(engine)
        existing_tables = set(inspector.get_table_names())
        with engine.begin() as connection:
            for table in Base.metadata.sorted_tables:
                if table.name not in existing_tables:
                    continue
                actual_columns = {column["name"] for column in inspector.get_columns(table.name)}
                missing_columns = [column.name for column in table.columns if column.name not in actual_columns]
                unexpected = [name for name in missing_columns if name != "tenant_id"]
                if unexpected:
                    raise RuntimeError(
                        f"Tabela {table.name} wymaga ręcznej migracji kolumn: {', '.join(unexpected)}"
                    )
                if "tenant_id" in missing_columns:
                    connection.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN tenant_id INTEGER NOT NULL DEFAULT 1'))
                    added_columns.append(f"{table.name}.tenant_id")

        before_create = set(inspect(engine).get_table_names())
        Base.metadata.create_all(engine)
        after_create = set(inspect(engine).get_table_names())
        created_tables = sorted(after_create - before_create)

        for table in Base.metadata.sorted_tables:
            if table.name not in after_create:
                continue
            for index in table.indexes:
                index.create(engine, checkfirst=True)

        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)"))
            connection.execute(text("DELETE FROM alembic_version"))
            connection.execute(text("INSERT INTO alembic_version(version_num) VALUES ('005')"))

        final_inspector = inspect(engine)
        missing: list[str] = []
        final_tables = set(final_inspector.get_table_names())
        for table in Base.metadata.sorted_tables:
            if table.name not in final_tables:
                missing.append(table.name)
                continue
            actual = {column["name"] for column in final_inspector.get_columns(table.name)}
            missing.extend(f"{table.name}.{column.name}" for column in table.columns if column.name not in actual)
        if missing:
            raise RuntimeError(f"Migracja SQLite jest niekompletna: {', '.join(missing)}")

        return {
            "database": str(database),
            "backup": str(backup) if backup else None,
            "added_columns": added_columns,
            "created_tables": created_tables,
            "revision": "005",
        }
    finally:
        engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Aktualizuje lokalną bazę SQLite FreshStock bez utraty danych.")
    parser.add_argument("database", nargs="?", type=Path, default=Path(__file__).with_name("freshstock.db"))
    parser.add_argument("--no-backup", action="store_true", help="Nie twórz kopii zapasowej (tylko dla baz tymczasowych).")
    args = parser.parse_args()
    print(json.dumps(upgrade_sqlite(args.database, create_backup=not args.no_backup), ensure_ascii=False))


if __name__ == "__main__":
    main()
