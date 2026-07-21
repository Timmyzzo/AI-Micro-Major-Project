"""Unit tests for deterministic M2 source parsing and quality checks."""

from __future__ import annotations

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from powerinsight.data.validation import DataValidationError, validate_frame
from tests.data.fixtures import raw_minute_frame


def test_two_and_four_digit_years_are_parsed_day_first() -> None:
    timestamps = pd.to_datetime(["2007-02-01 00:00:00", "2007-02-01 00:01:00"])
    raw = raw_minute_frame(timestamps, four_digit_year_positions={1})

    result = validate_frame(raw)

    assert result.frame["timestamp"].tolist() == list(timestamps)


def test_question_mark_and_blank_become_nan_not_zero() -> None:
    timestamps = pd.date_range("2007-01-01", periods=2, freq="1min")
    raw = raw_minute_frame(timestamps, missing_positions={1})

    result = validate_frame(raw)

    assert result.report.measurement_missing_row_count == 1
    assert result.frame.loc[1, "global_active_power_kw"] != 0
    assert pd.isna(result.frame.loc[1, "global_active_power_kw"])
    assert pd.isna(result.frame.loc[1, "sub_metering_3_wh"])


def test_missing_block_boundaries_and_length_are_exact() -> None:
    timestamps = pd.date_range("2007-01-01", periods=8, freq="1min")
    raw = raw_minute_frame(timestamps, missing_positions={2, 3, 4})

    result = validate_frame(raw)

    assert len(result.report.missing_blocks) == 1
    block = result.report.missing_blocks[0]
    assert block.start_time == timestamps[2].to_pydatetime()
    assert block.end_time == timestamps[4].to_pydatetime()
    assert block.length_minutes == 3


def test_validation_stably_sorts_and_reports_duplicates() -> None:
    timestamps = pd.to_datetime(
        ["2007-01-01 00:01:00", "2007-01-01 00:00:00", "2007-01-01 00:01:00"]
    )
    raw = raw_minute_frame(timestamps)

    result = validate_frame(raw)

    assert result.frame["timestamp"].is_monotonic_increasing
    assert result.report.duplicate_count == 1
    codes = {issue.code for issue in result.report.issues}
    assert "DATA_TIMESTAMP_DUPLICATE" in codes
    assert "DATA_TIMESTAMP_SORTED" in codes


def test_invalid_date_is_a_blocking_error() -> None:
    raw = raw_minute_frame(pd.date_range("2007-01-01", periods=1, freq="1min"))
    raw.loc[0, "Date"] = "31/2/2007"

    with pytest.raises(DataValidationError, match="DATA_TIMESTAMP_INVALID"):
        validate_frame(raw)


def test_invalid_numeric_is_nan_and_reported() -> None:
    raw = raw_minute_frame(pd.date_range("2007-01-01", periods=2, freq="1min"))
    raw.loc[1, "Voltage"] = "not-a-number"

    result = validate_frame(raw)

    assert pd.isna(result.frame.loc[1, "voltage_v"])
    assert "DATA_NUMERIC_INVALID" in {issue.code for issue in result.report.issues}


def test_missing_required_column_is_a_blocking_error() -> None:
    raw = raw_minute_frame(pd.date_range("2007-01-01", periods=1, freq="1min")).drop(
        columns="Global_active_power"
    )

    with pytest.raises(DataValidationError, match="Global_active_power"):
        validate_frame(raw)


def test_validation_does_not_modify_the_callers_dataframe() -> None:
    raw = raw_minute_frame(pd.date_range("2007-01-01", periods=3, freq="1min"))
    original = raw.copy(deep=True)

    validate_frame(raw)

    assert_frame_equal(raw, original)
