"""SQLite schema and idempotency tests."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from powerinsight.data.validation import validate_frame
from powerinsight.persistence.database import (
    EXPECTED_TABLES,
    SCHEMA_VERSION,
    database_health,
    initialize_database,
)
from powerinsight.persistence.metadata import (
    complete_preprocess_run,
    fail_preprocess_run,
    register_dataset,
    start_preprocess_run,
)
from powerinsight.schemas import ProcessedDatasetRecord
from tests.data.fixtures import raw_minute_frame


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


def test_dataset_and_completed_preprocess_registration_are_idempotent(tmp_path: Path) -> None:
    database_path = tmp_path / "metadata.db"
    validation = validate_frame(
        raw_minute_frame(pd.date_range("2007-01-01", periods=15, freq="1min"))
    )
    register_dataset(database_path, validation.dataset, validation.report)
    register_dataset(database_path, validation.dataset, validation.report)
    start_preprocess_run(
        database_path,
        preprocess_id="prep_test",
        dataset_id=validation.dataset.dataset_id,
        config_hash="A" * 64,
        output_path_alias="data/processed/prep_test/power_15min.parquet",
    )
    record = ProcessedDatasetRecord(
        schema_version="1.0",
        preprocess_id="prep_test",
        dataset_id=validation.dataset.dataset_id,
        config_hash="A" * 64,
        minute_path_alias="data/interim/prep_test/minute.parquet",
        processed_path_alias="data/processed/prep_test/power_15min.parquet",
        manifest_path_alias="data/manifests/test.json",
        minute_rows=15,
        processed_rows=1,
        split_counts={"train": 1, "validation": 0, "test": 0},
        status="completed",
        created_at=datetime.now(UTC),
    )
    complete_preprocess_run(database_path, record, summary={"processed_rows": 1})
    start_preprocess_run(
        database_path,
        preprocess_id="prep_test",
        dataset_id=validation.dataset.dataset_id,
        config_hash="A" * 64,
        output_path_alias=record.processed_path_alias,
    )
    complete_preprocess_run(database_path, record, summary={"processed_rows": 1})

    with sqlite3.connect(database_path) as connection:
        dataset_rows = connection.execute("SELECT COUNT(*) FROM datasets").fetchone()
        preprocess_rows = connection.execute("SELECT COUNT(*) FROM preprocess_runs").fetchone()
        status = connection.execute(
            "SELECT status FROM preprocess_runs WHERE preprocess_id = ?", ("prep_test",)
        ).fetchone()

    assert dataset_rows == (1,)
    assert preprocess_rows == (1,)
    assert status == ("completed",)


def test_failed_preprocess_run_is_not_marked_completed(tmp_path: Path) -> None:
    database_path = tmp_path / "metadata.db"
    validation = validate_frame(
        raw_minute_frame(pd.date_range("2007-01-01", periods=2, freq="1min"))
    )
    register_dataset(database_path, validation.dataset, validation.report)
    start_preprocess_run(
        database_path,
        preprocess_id="prep_failed",
        dataset_id=validation.dataset.dataset_id,
        config_hash="B" * 64,
        output_path_alias="data/processed/prep_failed/power_15min.parquet",
    )
    fail_preprocess_run(
        database_path,
        preprocess_id="prep_failed",
        error_code="PREP_TEST_FAILURE",
        message="synthetic failure",
    )

    with sqlite3.connect(database_path) as connection:
        row = connection.execute(
            "SELECT status, summary_json FROM preprocess_runs WHERE preprocess_id = ?",
            ("prep_failed",),
        ).fetchone()

    assert row is not None
    assert row[0] == "failed"
    assert "PREP_TEST_FAILURE" in row[1]
