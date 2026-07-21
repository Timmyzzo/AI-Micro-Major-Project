"""Aggregate-only advice snapshot integration test."""

from pathlib import Path

import pandas as pd

from powerinsight.data.catalog import compute_sha256
from powerinsight.services.advice_service import build_advice_snapshot
from powerinsight.services.data_service import DataService
from tests.data.fixtures import raw_minute_frame
from tests.data.runtime import make_runtime_context


def test_advice_snapshot_contains_aggregates_without_raw_series_or_paths(tmp_path: Path) -> None:
    context = make_runtime_context(tmp_path)
    context.paths.builtin_csv.parent.mkdir(parents=True, exist_ok=True)
    raw_minute_frame(pd.date_range("2007-01-01", periods=90, freq="1min")).to_csv(
        context.paths.builtin_csv,
        index=False,
    )
    DataService(
        context,
        expected_sha256=compute_sha256(context.paths.builtin_csv),
    ).prepare_builtin()

    snapshot = build_advice_snapshot(context)

    assert snapshot.evidence["dataset_id"]
    assert snapshot.evidence["coverage_ratio"] == 1.0
    assert "raw_series" not in snapshot.evidence
    assert "path" not in " ".join(snapshot.evidence).lower()
    assert len(snapshot.evidence) <= 11
