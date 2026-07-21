"""Unit tests for M2 missing policy, features, aggregation, and time splits."""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from powerinsight.data.preprocessing import (
    add_derived_fields,
    aggregate_minutes,
    apply_missing_policy,
    assign_fixed_splits,
    config_fingerprint,
)
from powerinsight.data.validation import validate_frame
from powerinsight.schemas import PreprocessConfig
from tests.data.fixtures import raw_minute_frame


def _config(
    *,
    short_gap_max_minutes: int = 60,
    bucket_min_valid_ratio: float = 0.8,
) -> PreprocessConfig:
    return PreprocessConfig(
        short_gap_max_minutes=short_gap_max_minutes,
        bucket_min_valid_ratio=bucket_min_valid_ratio,
        train_end=datetime(2007, 4, 30, 23, 59, 59),
        validation_end=datetime(2007, 5, 31, 23, 59, 59),
        test_end=datetime(2007, 6, 30, 23, 59, 59),
    )


@pytest.mark.parametrize("gap_length", (1, 2, 30, 60))
def test_short_gaps_are_interpolated_with_masks(gap_length: int) -> None:
    timestamps = pd.date_range("2007-01-01", periods=gap_length + 2, freq="1min")
    missing = set(range(1, gap_length + 1))
    validated = validate_frame(raw_minute_frame(timestamps, missing_positions=missing))

    result = apply_missing_policy(validated.frame, _config())

    assert int(result["missing_mask"].sum()) == gap_length
    assert int(result["imputed_mask"].sum()) == gap_length
    assert int(result["long_gap_mask"].sum()) == 0
    assert result.loc[result["missing_mask"], "global_active_power_kw"].notna().all()


@pytest.mark.parametrize("gap_length", (61, 2 * 24 * 60))
def test_long_gaps_remain_nan_and_are_protected(gap_length: int) -> None:
    timestamps = pd.date_range("2007-01-01", periods=gap_length + 2, freq="1min")
    missing = set(range(1, gap_length + 1))
    validated = validate_frame(raw_minute_frame(timestamps, missing_positions=missing))

    result = apply_missing_policy(validated.frame, _config())

    assert int(result["imputed_mask"].sum()) == 0
    assert int(result["long_gap_mask"].sum()) == gap_length
    assert result.loc[result["long_gap_mask"], "global_active_power_kw"].isna().all()


def test_energy_and_unmetered_formulas_are_correct() -> None:
    raw = raw_minute_frame(pd.date_range("2007-01-01", periods=1, freq="1min"))
    raw.loc[0, "Global_active_power"] = "1.2"
    validated = validate_frame(raw)
    prepared = apply_missing_policy(validated.frame, _config())

    result, negative_count = add_derived_fields(prepared, _config())

    assert result.loc[0, "global_active_energy_wh"] == pytest.approx(20.0)
    assert result.loc[0, "unmetered_energy_wh"] == pytest.approx(14.0)
    assert negative_count == 0


def test_significant_negative_unmetered_energy_is_retained_and_counted() -> None:
    raw = raw_minute_frame(pd.date_range("2007-01-01", periods=1, freq="1min"))
    raw.loc[0, "Global_active_power"] = "0.3"
    validated = validate_frame(raw)
    prepared = apply_missing_policy(validated.frame, _config())

    result, negative_count = add_derived_fields(prepared, _config())

    assert result.loc[0, "unmetered_energy_wh"] == pytest.approx(-1.0)
    assert bool(result.loc[0, "unmetered_negative_mask"])
    assert negative_count == 1


def test_aggregation_uses_mean_for_power_and_sum_for_energy() -> None:
    raw = raw_minute_frame(pd.date_range("2007-01-01", periods=15, freq="1min"))
    raw["Global_active_power"] = [str(value) for value in range(1, 16)]
    validated = validate_frame(raw)
    minute = apply_missing_policy(validated.frame, _config())
    minute, _ = add_derived_fields(minute, _config())

    result = aggregate_minutes(minute, _config())

    assert len(result) == 1
    assert result.loc[0, "global_active_power_kw"] == pytest.approx(8.0)
    assert result.loc[0, "sub_metering_1_wh"] == pytest.approx(15.0)
    assert result.loc[0, "global_active_energy_wh"] == pytest.approx(2000.0)


@pytest.mark.parametrize(("valid_minutes", "should_be_valid"), ((12, True), (11, False)))
def test_bucket_minimum_valid_ratio_boundary(valid_minutes: int, should_be_valid: bool) -> None:
    timestamps = pd.date_range("2007-01-01", periods=15, freq="1min")
    missing = set(range(valid_minutes, 15))
    validated = validate_frame(raw_minute_frame(timestamps, missing_positions=missing))
    minute = apply_missing_policy(validated.frame, _config(short_gap_max_minutes=0))
    minute, _ = add_derived_fields(minute, _config(short_gap_max_minutes=0))

    result = aggregate_minutes(minute, _config(short_gap_max_minutes=0))

    assert bool(pd.notna(result.loc[0, "global_active_power_kw"])) is should_be_valid


def test_fixed_month_splits_are_not_random() -> None:
    frame = pd.DataFrame(
        {"timestamp": pd.to_datetime(["2007-04-30 23:45", "2007-05-01 00:00", "2007-06-01 00:00"])}
    )

    result = assign_fixed_splits(frame, _config())

    assert result["split"].tolist() == ["train", "validation", "test"]


def test_config_fingerprint_is_stable_and_complete() -> None:
    first = _config()
    second = _config()
    changed = _config(bucket_min_valid_ratio=0.9)

    assert config_fingerprint(first) == config_fingerprint(second)
    assert config_fingerprint(first) != config_fingerprint(changed)


def test_preprocessing_functions_do_not_modify_input_frame() -> None:
    validated = validate_frame(
        raw_minute_frame(pd.date_range("2007-01-01", periods=15, freq="1min"))
    )
    original = validated.frame.copy(deep=True)

    apply_missing_policy(validated.frame, _config())

    assert_frame_equal(validated.frame, original)
