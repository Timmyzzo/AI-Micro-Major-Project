"""Idempotent SQLite metadata schema initialization."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

SCHEMA_VERSION = 1
EXPECTED_TABLES = (
    "alerts",
    "datasets",
    "forecasts",
    "model_runs",
    "optimization_scenarios",
    "preprocess_runs",
    "reports",
    "schema_versions",
    "settings",
)

MIGRATION_1: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS datasets (
        dataset_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        source_type TEXT NOT NULL,
        path_alias TEXT NOT NULL,
        sha256 TEXT NOT NULL UNIQUE,
        row_count INTEGER,
        start_time TEXT,
        end_time TEXT,
        status TEXT NOT NULL,
        metadata_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS preprocess_runs (
        preprocess_id TEXT PRIMARY KEY,
        dataset_id TEXT NOT NULL,
        config_hash TEXT NOT NULL,
        output_path_alias TEXT,
        status TEXT NOT NULL,
        summary_json TEXT NOT NULL DEFAULT '{}',
        started_at TEXT NOT NULL,
        completed_at TEXT,
        FOREIGN KEY (dataset_id) REFERENCES datasets(dataset_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS model_runs (
        run_id TEXT PRIMARY KEY,
        model_id TEXT,
        preprocess_id TEXT,
        model_type TEXT NOT NULL,
        config_hash TEXT NOT NULL,
        device TEXT NOT NULL,
        status TEXT NOT NULL,
        best_epoch INTEGER,
        metrics_json TEXT NOT NULL DEFAULT '{}',
        artifact_path_alias TEXT,
        started_at TEXT NOT NULL,
        completed_at TEXT,
        FOREIGN KEY (preprocess_id) REFERENCES preprocess_runs(preprocess_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS forecasts (
        forecast_id TEXT PRIMARY KEY,
        dataset_id TEXT NOT NULL,
        model_id TEXT NOT NULL,
        forecast_start TEXT NOT NULL,
        request_hash TEXT NOT NULL,
        status TEXT NOT NULL,
        artifact_path_alias TEXT,
        latency_ms REAL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (dataset_id) REFERENCES datasets(dataset_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS alerts (
        alert_id TEXT PRIMARY KEY,
        forecast_id TEXT,
        dataset_id TEXT NOT NULL,
        model_id TEXT,
        alert_type TEXT NOT NULL,
        severity TEXT NOT NULL,
        start_time TEXT NOT NULL,
        end_time TEXT NOT NULL,
        status TEXT NOT NULL,
        evidence_json TEXT NOT NULL DEFAULT '{}',
        note TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (forecast_id) REFERENCES forecasts(forecast_id),
        FOREIGN KEY (dataset_id) REFERENCES datasets(dataset_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS optimization_scenarios (
        scenario_id TEXT PRIMARY KEY,
        source_type TEXT NOT NULL,
        source_id TEXT NOT NULL,
        request_json TEXT NOT NULL,
        result_json TEXT,
        status TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS reports (
        report_id TEXT PRIMARY KEY,
        evidence_hash TEXT NOT NULL,
        generation_mode TEXT NOT NULL,
        provider_alias TEXT,
        model_alias TEXT,
        status TEXT NOT NULL,
        artifact_path_alias TEXT,
        diagnostics_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value_json TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
)


@dataclass(frozen=True)
class DatabaseInfo:
    """Verified database schema summary."""

    path: Path
    schema_version: int
    tables: tuple[str, ...]


def initialize_database(path: Path) -> DatabaseInfo:
    """Create the metadata schema once and safely return its current version."""
    resolved_path = path.resolve()
    resolved_path.parent.mkdir(parents=True, exist_ok=True)
    connection = connect_database(resolved_path)
    try:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_versions (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL
            )
            """
        )
        row = connection.execute("SELECT MAX(version) FROM schema_versions").fetchone()
        current_version = int(row[0]) if row and row[0] is not None else 0
        if current_version < SCHEMA_VERSION:
            with connection:
                for statement in MIGRATION_1:
                    connection.execute(statement)
                connection.execute(
                    "INSERT INTO schema_versions(version, applied_at) VALUES (?, ?)",
                    (SCHEMA_VERSION, datetime.now(UTC).isoformat()),
                )
        tables = _list_tables(connection)
        return DatabaseInfo(path=resolved_path, schema_version=SCHEMA_VERSION, tables=tables)
    finally:
        connection.close()


def database_health(path: Path) -> tuple[bool, str]:
    """Check that the database exists, is readable, and has the current migration."""
    resolved_path = path.resolve()
    if not resolved_path.is_file():
        return False, "数据库尚未初始化"
    try:
        connection = connect_database(resolved_path)
        try:
            check_row = connection.execute("PRAGMA quick_check").fetchone()
            version_row = connection.execute("SELECT MAX(version) FROM schema_versions").fetchone()
        finally:
            connection.close()
    except sqlite3.Error as exc:
        return False, f"数据库不可访问: {exc}"
    is_healthy = bool(check_row and check_row[0] == "ok") and bool(
        version_row and version_row[0] == SCHEMA_VERSION
    )
    return (True, f"可访问，schema v{SCHEMA_VERSION}") if is_healthy else (False, "schema 未就绪")


def connect_database(path: Path) -> sqlite3.Connection:
    """Open one SQLite metadata connection with foreign keys enabled."""
    connection = sqlite3.connect(path, timeout=5.0)
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _list_tables(connection: sqlite3.Connection) -> tuple[str, ...]:
    rows = connection.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    return tuple(str(row[0]) for row in rows)
