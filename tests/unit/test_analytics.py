"""Hand-checkable deterministic M3 analytics tests."""

from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from powerinsight.analytics import analyze_frame, downsample_trend


def _analysis_frame() -> pd.DataFrame:
    timestamps = pd.date_range("2007-01-01", periods=8, freq="15min")
    power = [1.0, 2.0, np.nan, 4.0, 2.0, 3.0, 1.0, 1.0]
    energy = [250.0, 500.0, np.nan, 1000.0, 500.0, 750.0, 250.0, 250.0]
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "global_active_power_kw": power,
            "global_active_energy_wh": energy,
            "sub_metering_1_wh": [50.0, 100.0, np.nan, 200.0, 100.0, 150.0, 50.0, 50.0],
            "sub_metering_2_wh": [25.0, 50.0, np.nan, 100.0, 50.0, 75.0, 25.0, 25.0],
            "sub_metering_3_wh": [25.0, 50.0, np.nan, 100.0, 50.0, 75.0, 25.0, 25.0],
            "unmetered_energy_wh": [150.0, 300.0, np.nan, 600.0, 300.0, 450.0, 150.0, 150.0],
            "missing_ratio": [0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            "imputed_ratio": 0.0,
            "long_gap": [False, False, True, False, False, False, False, False],
        }
    )


def test_range_boundaries_kpis_energy_coverage_and_input_immutability() -> None:
    frame = _analysis_frame()
    original = frame.copy(deep=True)

    result = analyze_frame(
        frame,
        preprocess_id="prep_fixture",
        start=datetime(2007, 1, 1, 0, 0),
        end_exclusive=datetime(2007, 1, 1, 1, 0),
        max_chart_points=100,
    )

    assert result.range_summary.expected_points == 4
    assert result.range_summary.actual_points == 4
    assert result.range_summary.valid_load_points == 3
    assert result.range_summary.missing_points == 1
    assert result.range_summary.coverage_ratio == pytest.approx(0.75)
    assert result.kpis.average_active_power_kw == pytest.approx(7 / 3)
    assert result.kpis.peak_active_power_kw == 4.0
    assert result.kpis.peak_time == datetime(2007, 1, 1, 0, 45)
    assert result.kpis.minimum_active_power_kw == 1.0
    assert result.kpis.minimum_time == datetime(2007, 1, 1, 0, 0)
    assert result.kpis.total_active_energy_kwh == pytest.approx(1.75)
    assert result.trend.loc[2, "global_active_power_kw"] is np.nan or pd.isna(
        result.trend.loc[2, "global_active_power_kw"]
    )
    assert result.status == "attention"
    pd.testing.assert_frame_equal(frame, original)


def test_empty_and_all_nan_ranges_keep_unknown_values() -> None:
    frame = _analysis_frame()
    empty = analyze_frame(
        frame,
        preprocess_id="prep_fixture",
        start=datetime(2007, 1, 2),
        end_exclusive=datetime(2007, 1, 2, 1),
        max_chart_points=100,
    )
    all_nan = analyze_frame(
        frame,
        preprocess_id="prep_fixture",
        start=datetime(2007, 1, 1, 0, 30),
        end_exclusive=datetime(2007, 1, 1, 0, 45),
        max_chart_points=100,
    )

    for result in (empty, all_nan):
        assert result.status == "empty"
        assert result.kpis.average_active_power_kw is None
        assert result.kpis.total_active_energy_kwh is None
        assert result.kpis.peak_active_power_kw is None
        assert result.kpis.minimum_active_power_kw is None


def test_hour_weekday_and_workday_weekend_profiles_have_counts_and_fixed_order() -> None:
    timestamps = pd.date_range("2007-01-01", periods=7 * 24 * 4, freq="15min")
    frame = pd.DataFrame(
        {
            "timestamp": timestamps,
            "global_active_power_kw": 1.0,
            "global_active_energy_wh": 250.0,
            "sub_metering_1_wh": 25.0,
            "sub_metering_2_wh": 25.0,
            "sub_metering_3_wh": 25.0,
            "unmetered_energy_wh": 175.0,
            "missing_ratio": 0.0,
            "imputed_ratio": 0.0,
            "long_gap": False,
        }
    )
    result = analyze_frame(
        frame,
        preprocess_id="prep_fixture",
        start=datetime(2007, 1, 1),
        end_exclusive=datetime(2007, 1, 8),
        max_chart_points=10000,
    )

    assert result.hourly_profile["hour"].tolist() == list(range(24))
    assert result.hourly_profile["valid_samples"].tolist() == [28] * 24
    assert result.weekday_profile["weekday_label"].tolist() == [
        "星期一",
        "星期二",
        "星期三",
        "星期四",
        "星期五",
        "星期六",
        "星期日",
    ]
    assert set(result.day_type_profile["day_type"]) == {"工作日", "周末"}
    assert (result.day_type_profile["coverage_ratio"] == 1.0).all()


def test_submeter_totals_shares_and_negative_unmetered_evidence() -> None:
    normal = analyze_frame(
        _analysis_frame().drop(index=2),
        preprocess_id="prep_fixture",
        start=datetime(2007, 1, 1),
        end_exclusive=datetime(2007, 1, 1, 2),
        max_chart_points=100,
    )
    negative_frame = _analysis_frame().drop(index=2).copy()
    negative_frame.loc[0, "unmetered_energy_wh"] = -1.0
    negative = analyze_frame(
        negative_frame,
        preprocess_id="prep_fixture",
        start=datetime(2007, 1, 1),
        end_exclusive=datetime(2007, 1, 1, 2),
        max_chart_points=100,
    )

    assert normal.submeter.shares_available is True
    assert sum(
        component.share_ratio or 0.0 for component in normal.submeter.components
    ) == pytest.approx(
        1.0,
        abs=1e-6,
    )
    assert negative.submeter.negative_unmetered_records == 1
    assert negative.submeter.shares_available is False
    assert all(component.share_ratio is None for component in negative.submeter.components)
    assert "原值已保留" in negative.submeter.note


def test_zero_total_does_not_fabricate_shares() -> None:
    frame = _analysis_frame().iloc[:1].copy()
    for column in (
        "global_active_energy_wh",
        "sub_metering_1_wh",
        "sub_metering_2_wh",
        "sub_metering_3_wh",
        "unmetered_energy_wh",
    ):
        frame[column] = 0.0
    result = analyze_frame(
        frame,
        preprocess_id="prep_fixture",
        start=datetime(2007, 1, 1),
        end_exclusive=datetime(2007, 1, 1, 0, 15),
        max_chart_points=100,
    )

    assert result.kpis.total_active_energy_kwh == 0.0
    assert result.submeter.shares_available is False
    assert all(component.share_ratio is None for component in result.submeter.components)


def test_downsampling_respects_limit_order_and_missing_breaks() -> None:
    frame = _analysis_frame()
    sampled = downsample_trend(frame, max_points=6)

    assert len(sampled) <= 6
    assert sampled["timestamp"].is_monotonic_increasing
    assert sampled["global_active_power_kw"].isna().any()
    assert sampled.iloc[0]["timestamp"] == frame.iloc[0]["timestamp"]
    assert sampled.iloc[-1]["timestamp"] == frame.iloc[-1]["timestamp"]
