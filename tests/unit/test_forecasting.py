"""Leakage, baseline, metric, and conformal coverage for M4."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from powerinsight.forecasting import (
    TargetScaler,
    WindowConfig,
    build_windows,
    calibrate_conformal,
    compute_forecast_metrics,
    compute_horizon_metrics,
    compute_step_metrics,
    interval_metrics,
    naive_predict,
)


def _processed_frame(periods: int = 900) -> pd.DataFrame:
    timestamp = pd.date_range("2007-01-01", periods=periods, freq="15min")
    return pd.DataFrame(
        {
            "timestamp": timestamp,
            "global_active_power_kw": np.linspace(0.5, 2.5, periods),
            "long_gap": False,
            "split": "train",
        }
    )


def test_build_windows_uses_exact_context_target_and_origin() -> None:
    frame = _processed_frame(20)
    result = build_windows(
        frame,
        split="train",
        config=WindowConfig(context_length=8, prediction_length=4, stride=4),
    )

    assert result.context.shape == (3, 8)
    assert result.target.shape == (3, 4)
    assert result.origins[0] == np.datetime64("2007-01-01T02:00:00")
    np.testing.assert_allclose(result.context[0], frame["global_active_power_kw"].iloc[:8])
    np.testing.assert_allclose(result.target[0], frame["global_active_power_kw"].iloc[8:12])


def test_build_windows_rejects_nan_and_long_gap_without_zero_fill() -> None:
    frame = _processed_frame(20)
    frame.loc[5, "global_active_power_kw"] = np.nan
    frame.loc[15, "long_gap"] = True
    result = build_windows(
        frame,
        split="train",
        config=WindowConfig(context_length=8, prediction_length=4, stride=1),
    )

    assert result.candidate_count == 9
    assert result.rejected_count == 9
    assert result.rejection_reasons["missing_or_long_gap"] == 9
    assert result.context.size == 0


def test_build_windows_rejects_time_discontinuity() -> None:
    frame = _processed_frame(14)
    frame.loc[9:, "timestamp"] += pd.Timedelta(minutes=15)
    result = build_windows(
        frame,
        split="train",
        config=WindowConfig(context_length=8, prediction_length=4),
    )

    assert result.rejection_reasons["discontinuous_time"] == 3


def test_build_windows_never_crosses_split_boundary() -> None:
    frame = _processed_frame(24)
    frame.loc[12:, "split"] = "validation"
    train = build_windows(
        frame,
        split="train",
        config=WindowConfig(context_length=8, prediction_length=4),
    )
    validation = build_windows(
        frame,
        split="validation",
        config=WindowConfig(context_length=8, prediction_length=4),
    )

    assert train.context.shape == (1, 8)
    assert validation.context.shape == (1, 8)
    assert train.origins[0] < np.datetime64("2007-01-01T03:00:00")
    assert validation.origins[0] >= np.datetime64("2007-01-01T05:00:00")


def test_target_scaler_only_fits_train_and_roundtrips() -> None:
    values = np.array([1.0, 2.0, 3.0, 10.0], dtype=np.float32)
    scaler = TargetScaler.fit(values, split="train")

    np.testing.assert_allclose(scaler.inverse_transform(scaler.transform(values)), values)
    assert scaler.fitted_split == "train"
    with pytest.raises(ValueError, match="training split"):
        TargetScaler.fit(values, split="test")


def test_target_scaler_saved_contract_rejects_non_train_fit() -> None:
    with pytest.raises(ValueError, match="training split"):
        TargetScaler.from_dict({"center": 1.0, "scale": 2.0, "fitted_split": "validation"})


def test_naive_baselines_use_only_formal_history() -> None:
    context = np.arange(672, dtype=np.float32).reshape(1, -1)

    np.testing.assert_array_equal(naive_predict(context, "last_value", prediction_length=96), 671)
    np.testing.assert_array_equal(
        naive_predict(context, "seasonal_day", prediction_length=96), context[:, -96:]
    )
    np.testing.assert_array_equal(
        naive_predict(context, "seasonal_week", prediction_length=96), context[:, :96]
    )


def test_metrics_match_hand_calculation_and_keep_ratios_unscaled() -> None:
    true = np.array([[1.0, 2.0], [3.0, 4.0]])
    pred = np.array([[1.0, 1.0], [5.0, 4.0]])
    metrics = compute_forecast_metrics(true, pred)

    assert metrics.mae == pytest.approx(0.75)
    assert metrics.rmse == pytest.approx(np.sqrt(1.25))
    assert metrics.wape == pytest.approx(0.3)
    assert 0.0 <= metrics.smape <= 2.0


def test_step_and_hour_horizon_metrics_have_expected_shapes() -> None:
    true = np.ones((3, 96), dtype=np.float32)
    pred = np.zeros((3, 96), dtype=np.float32)

    steps = compute_step_metrics(true, pred)
    horizons = compute_horizon_metrics(true, pred)

    assert len(steps) == 96
    assert steps[-1]["minutes"] == 1440
    assert tuple(horizons) == ("1h", "6h", "12h", "24h")
    assert horizons["24h"]["mae"] == pytest.approx(1.0)


def test_conformal_uses_per_step_validation_residuals() -> None:
    true = np.zeros((9, 3), dtype=np.float32)
    pred = np.column_stack([np.arange(1, 10), np.arange(2, 20, 2), np.arange(3, 30, 3)]).astype(
        np.float32
    )

    quantiles = calibrate_conformal(true, pred, interval_level=0.9)

    assert quantiles.shape == (3,)
    assert quantiles[0] < quantiles[1] < quantiles[2]


def test_interval_metrics_clip_physical_lower_bound_and_report_steps() -> None:
    true = np.array([[0.1, 2.0], [0.2, 3.0]], dtype=np.float32)
    pred = np.array([[0.0, 2.5], [0.1, 2.5]], dtype=np.float32)
    result = interval_metrics(true, pred, np.array([1.0, 1.0], dtype=np.float32))

    assert result["coverage"] == pytest.approx(1.0)
    assert len(result["step_coverage"]) == 2
    assert float(result["average_width_kw"]) < 2.0
