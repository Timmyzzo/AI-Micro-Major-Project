"""SQLite schema and idempotency tests."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from powerinsight.persistence.database import (
    EXPECTED_TABLES,
    SCHEMA_VERSION,
    database_health,
    initialize_database,
)


def test_database_initialization_is_idempotent(tmp_path: Path) -> None:
    database_path = tmp_path / "metadata.db"

    first = initialize_database(database_path)
    second = initialize_database(database_path)

    assert first.schema_version == SCHEMA_VERSION
    assert second.schema_version == SCHEMA_VERSION
    assert first.tables == EXPECTED_TABLES
    assert second.tables == EXPECTED_TABLES

    with sqlite3.connect(database_path) as connection:
        version_rows = connection.execute("SELECT version FROM schema_versions").fetchall()
    assert version_rows == [(SCHEMA_VERSION,)]


def test_database_has_metadata_tables_and_foreign_keys(tmp_path: Path) -> None:
    database_path = tmp_path / "metadata.db"
    initialize_database(database_path)

    with sqlite3.connect(database_path) as connection:
        foreign_keys = connection.execute("PRAGMA foreign_key_list(preprocess_runs)").fetchall()
        settings_rows = connection.execute("SELECT COUNT(*) FROM settings").fetchone()

    assert any(row[2] == "datasets" for row in foreign_keys)
    assert settings_rows == (0,)
    assert "raw_measurements" not in EXPECTED_TABLES


def test_database_health_reports_current_schema(tmp_path: Path) -> None:
    database_path = tmp_path / "metadata.db"
    initialize_database(database_path)

    healthy, detail = database_health(database_path)

    assert healthy is True
    assert detail == f"可访问，schema v{SCHEMA_VERSION}"
