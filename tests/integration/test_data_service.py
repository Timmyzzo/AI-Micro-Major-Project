"""Data service integration across files, manifest, Parquet, and SQLite metadata."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

from powerinsight.data.catalog import compute_sha256
from powerinsight.services.data_service import DataService
from tests.data.fixtures import raw_minute_frame
from tests.data.runtime import make_runtime_context


def test_data_service_empty_then_completed_state_and_safe_rerun(tmp_path: Path) -> None:
    context = make_runtime_context(tmp_path)
    context.paths.builtin_csv.parent.mkdir(parents=True, exist_ok=True)
    raw_minute_frame(pd.date_range("2007-01-01", periods=30, freq="1min")).to_csv(
        context.paths.builtin_csv,
        index=False,
    )
    expected_sha256 = compute_sha256(context.paths.builtin_csv)
    service = DataService(context, expected_sha256=expected_sha256)

    empty_state = service.inspect_builtin_state()
    first = service.prepare_builtin()
    second = service.prepare_builtin()
    completed_state = service.inspect_builtin_state()

    assert empty_state.manifest is None
    assert empty_state.processed_exists is False
    assert first.processed.preprocess_id == second.processed.preprocess_id
    assert first.processed.config_hash == second.processed.config_hash
    assert first.processed.processed_rows == 2
    assert completed_state.manifest is not None
    assert completed_state.processed_exists is True
    assert len(service.load_processed_preview(first.manifest, rows=1)) == 1

    with sqlite3.connect(context.paths.database_path) as connection:
        dataset_count = connection.execute("SELECT COUNT(*) FROM datasets").fetchone()
        preprocess_count = connection.execute("SELECT COUNT(*) FROM preprocess_runs").fetchone()
        status = connection.execute("SELECT status FROM preprocess_runs").fetchone()
    assert dataset_count == (1,)
    assert preprocess_count == (1,)
    assert status == ("completed",)
