"""Additive schema alignment for databases created before the allergen-ledger feature.

The project uses Base.metadata.create_all (no alembic), which creates new tables
but never ALTERs existing ones. These guarded ALTERs bring an old Postgres/SQLite
database up to date; fresh databases get everything from create_all + server defaults.
"""
from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


def _has_column(insp, table: str, column: str) -> bool:
    return any(c["name"] == column for c in insp.get_columns(table))


def _has_index(insp, table: str, index: str) -> bool:
    return any(ix["name"] == index for ix in insp.get_indexes(table))


def ensure_schema(engine: Engine) -> None:
    insp = inspect(engine)
    table_names = set(insp.get_table_names())
    statements: list[str] = []

    if "ingredients" in table_names:
        cols = insp.get_columns("ingredients")
        if not _has_column(insp, "ingredients", "is_allergen"):
            statements.append(
                "ALTER TABLE ingredients ADD COLUMN is_allergen BOOLEAN NOT NULL DEFAULT false"
            )
        if not _has_column(insp, "ingredients", "occupied_qty"):
            statements.append(
                "ALTER TABLE ingredients ADD COLUMN occupied_qty FLOAT NOT NULL DEFAULT 0"
            )

    if "prep_runs" in table_names and not _has_column(insp, "prep_runs", "fingerprint"):
        statements.append("ALTER TABLE prep_runs ADD COLUMN fingerprint VARCHAR(64)")
        if not _has_index(insp, "prep_runs", "ux_prep_runs_fingerprint"):
            statements.append(
                "CREATE UNIQUE INDEX ux_prep_runs_fingerprint ON prep_runs (fingerprint)"
            )

    if not statements:
        return
    with engine.begin() as conn:
        for stmt in statements:
            conn.execute(text(stmt))
