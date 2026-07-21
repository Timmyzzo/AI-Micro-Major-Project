"""Full immutable CSV validation against independently documented facts."""

from __future__ import annotations

from powerinsight.data import BUILTIN_CSV_SHA256, validate_csv
from powerinsight.paths import PROJECT_ROOT


def test_builtin_csv_quality_contract() -> None:
    path = PROJECT_ROOT / "docs" / "household_power_consumption.csv"

    result = validate_csv(
        path,
        path_alias="docs/household_power_consumption.csv",
        expected_sha256=BUILTIN_CSV_SHA256,
    )

    assert result.dataset.sha256 == BUILTIN_CSV_SHA256
    assert result.dataset.row_count == 260_640
    assert result.dataset.field_count == 10
    assert result.dataset.start_time is not None
    assert result.dataset.end_time is not None
    assert result.dataset.start_time.isoformat() == "2007-01-01T00:00:00"
    assert result.dataset.end_time.isoformat() == "2007-06-30T23:59:00"
    assert result.dataset.cadence == "1min"
    assert result.report.measurement_missing_row_count == 3_771
    assert len(result.report.missing_blocks) == 13
    longest = max(result.report.missing_blocks, key=lambda block: block.length_minutes)
    assert longest.length_minutes == 3_723
    assert longest.start_time.isoformat() == "2007-04-28T00:21:00"
    assert longest.end_time.isoformat() == "2007-04-30T14:23:00"
