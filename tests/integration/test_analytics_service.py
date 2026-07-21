"""Read-only M3 service tests across manifest, Parquet, identity, and cache."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

import powerinsight.services.analytics_service as analytics_module
from powerinsight.data.catalog import compute_sha256
from powerinsight.services.analytics_service import (
    REQUIRED_COLUMNS,
    AnalyticsError,
    AnalyticsService,
    clear_analytics_cache,
)
from powerinsight.services.data_service import DataService
from powerinsight.services.runtime import RuntimeContext
from tests.data.fixtures import raw_minute_frame
from tests.data.runtime import make_runtime_context


def _prepared_context(root: Path, *, power_kw: float = 1.2) -> RuntimeContext:
    context = make_runtime_context(root)
    context.paths.builtin_csv.parent.mkdir(parents=True, exist_ok=True)
    source = raw_minute_frame(pd.date_range("2007-01-01", periods=90, freq="1min"))
    source["Global_active_power"] = str(power_kw)
    source.to_csv(context.paths.builtin_csv, index=False)
    DataService(
        context,
        expected_sha256=compute_sha256(context.paths.builtin_csv),
    ).prepare_builtin()
    return context


def test_service_reads_only_required_parquet_columns_and_respects_date_bounds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_analytics_cache()
    context = _prepared_context(tmp_path)
    original_read = pd.read_parquet
    calls: list[list[str] | None] = []

    def recording_read(path: object, *, columns: list[str] | None = None) -> pd.DataFrame:
        calls.append(columns)
        return original_read(path, columns=columns)

    monkeypatch.setattr(analytics_module.pd, "read_parquet", recording_read)
    database_mtime = context.paths.database_path.stat().st_mtime_ns
    result = AnalyticsService(context).analyze(
        start=datetime(2007, 1, 1, 0, 15),
        end_exclusive=datetime(2007, 1, 1, 1, 0),
    )

    assert calls == [list(REQUIRED_COLUMNS)]
    assert result.range_summary.actual_start == datetime(2007, 1, 1, 0, 15)
    assert result.range_summary.actual_end == datetime(2007, 1, 1, 0, 45)
    assert context.paths.database_path.stat().st_mtime_ns == database_mtime


def test_service_blocks_missing_manifest_and_processed_file(tmp_path: Path) -> None:
    missing_manifest_context = make_runtime_context(tmp_path / "manifest")
    missing_manifest_context.paths.builtin_csv.parent.mkdir(parents=True, exist_ok=True)
    raw_minute_frame(pd.date_range("2007-01-01", periods=30, freq="1min")).to_csv(
        missing_manifest_context.paths.builtin_csv,
        index=False,
    )
    availability = AnalyticsService(missing_manifest_context).inspect_availability()
    assert availability.status == "blocked"
    assert "ANALYTICS_MANIFEST_MISSING" in availability.evidence

    processed_context = _prepared_context(tmp_path / "processed")
    state = DataService(processed_context).inspect_builtin_state()
    assert state.manifest is not None
    processed_path = (
        processed_context.paths.data_dir
        / "processed"
        / state.manifest.preprocess_id
        / "power_15min.parquet"
    )
    processed_path.unlink()
    availability = AnalyticsService(processed_context).inspect_availability()
    assert availability.status == "blocked"
    assert "ANALYTICS_PARQUET_MISSING" in availability.evidence


def test_service_rejects_manifest_schema_incompatibility(tmp_path: Path) -> None:
    context = _prepared_context(tmp_path)
    state = DataService(context).inspect_builtin_state()
    assert state.manifest_path_alias is not None
    manifest_path = context.paths.root / state.manifest_path_alias
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    del payload["columns"]["global_active_energy_wh"]
    manifest_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    availability = AnalyticsService(context).inspect_availability()

    assert availability.status == "blocked"
    assert "ANALYTICS_MANIFEST_COLUMNS_MISSING" in availability.evidence


def test_cache_isolated_by_artifact_path_and_identity(tmp_path: Path) -> None:
    clear_analytics_cache()
    first_context = _prepared_context(tmp_path / "first", power_kw=1.2)
    second_context = _prepared_context(tmp_path / "second", power_kw=2.4)

    first = AnalyticsService(first_context).analyze(
        start=datetime(2007, 1, 1),
        end_exclusive=datetime(2007, 1, 1, 1),
    )
    second = AnalyticsService(second_context).analyze(
        start=datetime(2007, 1, 1),
        end_exclusive=datetime(2007, 1, 1, 1),
    )

    assert first.kpis.average_active_power_kw == pytest.approx(1.2)
    assert second.kpis.average_active_power_kw == pytest.approx(2.4)


def test_service_never_reads_raw_csv_for_aggregation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_analytics_cache()
    context = _prepared_context(tmp_path)

    def fail_read_csv(*args: object, **kwargs: object) -> None:
        raise AssertionError("M3 must not aggregate from raw CSV")

    monkeypatch.setattr(pd, "read_csv", fail_read_csv)

    result = AnalyticsService(context).analyze(
        start=datetime(2007, 1, 1),
        end_exclusive=datetime(2007, 1, 1, 1),
    )

    assert result.kpis.average_active_power_kw == pytest.approx(1.2)


def test_invalid_date_range_returns_display_safe_failure(tmp_path: Path) -> None:
    clear_analytics_cache()
    context = _prepared_context(tmp_path)

    with pytest.raises(AnalyticsError) as exc_info:
        AnalyticsService(context).analyze(
            start=datetime(2007, 1, 2),
            end_exclusive=datetime(2007, 1, 1),
        )

    assert exc_info.value.code == "ANALYTICS_QUERY_FAILED"
    assert str(context.paths.root) not in exc_info.value.reason
