"""Run a read-only, reproducible M3 acceptance against the current M2 artifact."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import statistics
import time
from datetime import datetime, timedelta
from datetime import time as datetime_time
from pathlib import Path

from powerinsight.services.analytics_service import AnalyticsService, clear_analytics_cache
from powerinsight.services.runtime import initialize_runtime


def main() -> None:
    """Print measured full-range M3 facts as UTF-8 JSON."""
    context = initialize_runtime()
    schema_hash = _sqlite_schema_hash(context.paths.database_path)
    service = AnalyticsService(context)

    clear_analytics_cache()
    inspect_started = time.perf_counter()
    availability = service.inspect_availability()
    inspect_seconds = time.perf_counter() - inspect_started
    if (
        availability.status != "ready"
        or availability.start_time is None
        or availability.end_time is None
        or availability.manifest is None
    ):
        raise RuntimeError(f"M3 acceptance blocked: {availability.title}: {availability.reason}")

    start = datetime.combine(availability.start_time.date(), datetime_time.min)
    end_exclusive = datetime.combine(
        availability.end_time.date() + timedelta(days=1),
        datetime_time.min,
    )
    cold_seconds: list[float] = []
    warm_seconds: list[float] = []
    result = None
    warm_result = None
    for _ in range(5):
        clear_analytics_cache()
        cold_started = time.perf_counter()
        result = service.analyze(start=start, end_exclusive=end_exclusive)
        cold_seconds.append(time.perf_counter() - cold_started)
        warm_started = time.perf_counter()
        warm_result = service.analyze(start=start, end_exclusive=end_exclusive)
        warm_seconds.append(time.perf_counter() - warm_started)
    assert result is not None
    assert warm_result is not None

    payload = {
        "dataset_id": availability.manifest.dataset_id,
        "preprocess_id": availability.manifest.preprocess_id,
        "analysis_start": start.isoformat(),
        "analysis_end_inclusive_date": (end_exclusive - timedelta(days=1)).date().isoformat(),
        "expected_points": result.range_summary.expected_points,
        "actual_points": result.range_summary.actual_points,
        "valid_points": result.range_summary.valid_load_points,
        "missing_points": result.range_summary.missing_points,
        "coverage_ratio": result.range_summary.coverage_ratio,
        "total_active_energy_kwh": result.kpis.total_active_energy_kwh,
        "average_active_power_kw": result.kpis.average_active_power_kw,
        "peak_active_power_kw": result.kpis.peak_active_power_kw,
        "peak_time": _iso(result.kpis.peak_time),
        "minimum_active_power_kw": result.kpis.minimum_active_power_kw,
        "minimum_time": _iso(result.kpis.minimum_time),
        "hourly_buckets": len(result.hourly_profile),
        "weekday_buckets": len(result.weekday_profile),
        "day_type_hour_buckets": len(result.day_type_profile),
        "submeter_kwh": {
            component.key: component.energy_kwh for component in result.submeter.components
        },
        "shares_available": result.submeter.shares_available,
        "negative_unmetered_records": result.submeter.negative_unmetered_records,
        "has_long_gap": result.has_long_gap,
        "status": result.status,
        "chart_points": len(result.trend),
        "max_chart_points": context.settings.ui.max_chart_points,
        "availability_inspect_seconds": inspect_seconds,
        "cold_query_analysis_seconds": cold_seconds,
        "cold_query_analysis_median_seconds": statistics.median(cold_seconds),
        "cold_query_analysis_max_seconds": max(cold_seconds),
        "warm_query_analysis_seconds": warm_seconds,
        "warm_query_analysis_median_seconds": statistics.median(warm_seconds),
        "warm_query_analysis_max_seconds": max(warm_seconds),
        "warm_same_kpi": warm_result.kpis == result.kpis,
        "sqlite_schema_sha256": schema_hash,
        "evidence": result.evidence,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _sqlite_schema_hash(path: Path) -> str:
    with sqlite3.connect(path) as connection:
        rows = connection.execute(
            "SELECT sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY type, name"
        ).fetchall()
    schema = "\n".join(str(row[0] or "") for row in rows)
    return hashlib.sha256(schema.encode("utf-8")).hexdigest().upper()


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


if __name__ == "__main__":
    main()
