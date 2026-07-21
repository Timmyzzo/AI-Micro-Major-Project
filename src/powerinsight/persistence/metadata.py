"""Parameterized and idempotent SQLite metadata registration."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from powerinsight.persistence.database import connect_database, initialize_database
from powerinsight.schemas import DataQualityReport, DatasetRecord, ProcessedDatasetRecord


def register_dataset(
    database_path: Path,
    dataset: DatasetRecord,
    report: DataQualityReport,
) -> None:
    """Insert or refresh one stable dataset identity without duplicating rows."""
    initialize_database(database_path)
    metadata_json = json.dumps(
        {
            "schema_version": dataset.schema_version,
            "size_bytes": dataset.size_bytes,
            "field_count": dataset.field_count,
            "cadence": dataset.cadence,
            "quality_status": report.status,
            "quality_score": report.score,
            "measurement_missing_rows": report.measurement_missing_row_count,
            "missing_blocks": len(report.missing_blocks),
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    connection = connect_database(database_path)
    try:
        with connection:
            connection.execute(
                """
                INSERT INTO datasets(
                    dataset_id, name, source_type, path_alias, sha256, row_count,
                    start_time, end_time, status, metadata_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(dataset_id) DO UPDATE SET
                    name = excluded.name,
                    source_type = excluded.source_type,
                    path_alias = excluded.path_alias,
                    sha256 = excluded.sha256,
                    row_count = excluded.row_count,
                    start_time = excluded.start_time,
                    end_time = excluded.end_time,
                    status = excluded.status,
                    metadata_json = excluded.metadata_json
                """,
                (
                    dataset.dataset_id,
                    dataset.name,
                    dataset.source_type,
                    dataset.path_alias,
                    dataset.sha256,
                    dataset.row_count,
                    dataset.start_time.isoformat() if dataset.start_time else None,
                    dataset.end_time.isoformat() if dataset.end_time else None,
                    dataset.status,
                    metadata_json,
                    dataset.created_at.isoformat(),
                ),
            )
    finally:
        connection.close()


def start_preprocess_run(
    database_path: Path,
    *,
    preprocess_id: str,
    dataset_id: str,
    config_hash: str,
    output_path_alias: str,
) -> None:
    """Create or restart one stable preprocessing run in running state."""
    initialize_database(database_path)
    started_at = datetime.now(UTC).isoformat()
    connection = connect_database(database_path)
    try:
        with connection:
            connection.execute(
                """
                INSERT INTO preprocess_runs(
                    preprocess_id, dataset_id, config_hash, output_path_alias,
                    status, summary_json, started_at, completed_at
                ) VALUES (?, ?, ?, ?, 'running', '{}', ?, NULL)
                ON CONFLICT(preprocess_id) DO UPDATE SET
                    dataset_id = excluded.dataset_id,
                    config_hash = excluded.config_hash,
                    output_path_alias = excluded.output_path_alias,
                    status = 'running',
                    summary_json = '{}',
                    started_at = excluded.started_at,
                    completed_at = NULL
                """,
                (preprocess_id, dataset_id, config_hash, output_path_alias, started_at),
            )
    finally:
        connection.close()


def complete_preprocess_run(
    database_path: Path,
    record: ProcessedDatasetRecord,
    *,
    summary: dict[str, object],
) -> None:
    """Mark an existing preprocessing run completed with non-sensitive statistics."""
    _finish_preprocess_run(
        database_path,
        preprocess_id=record.preprocess_id,
        status="completed",
        summary=summary,
    )


def fail_preprocess_run(
    database_path: Path,
    *,
    preprocess_id: str,
    error_code: str,
    message: str,
) -> None:
    """Record a failed run without storing paths, secrets, or a traceback."""
    _finish_preprocess_run(
        database_path,
        preprocess_id=preprocess_id,
        status="failed",
        summary={"error_code": error_code, "message": message},
    )


def _finish_preprocess_run(
    database_path: Path,
    *,
    preprocess_id: str,
    status: str,
    summary: dict[str, object],
) -> None:
    completed_at = datetime.now(UTC).isoformat()
    summary_json = json.dumps(summary, ensure_ascii=False, sort_keys=True)
    connection = connect_database(database_path)
    try:
        with connection:
            cursor = connection.execute(
                """
                UPDATE preprocess_runs
                SET status = ?, summary_json = ?, completed_at = ?
                WHERE preprocess_id = ?
                """,
                (status, summary_json, completed_at, preprocess_id),
            )
            if cursor.rowcount != 1:
                raise ValueError(f"preprocess run is not registered: {preprocess_id}")
    finally:
        connection.close()
