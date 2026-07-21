"""Pure forecasting data, metric, baseline, and conformal calculations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd  # type: ignore[import-untyped]

SplitName = Literal["train", "validation", "test"]
NaiveModelName = Literal["last_value", "seasonal_day", "seasonal_week"]


@dataclass(frozen=True)
class WindowConfig:
    """Formal direct multi-step window settings."""

    context_length: int = 672
    prediction_length: int = 96
    cadence_minutes: int = 15
    stride: int = 1

    def __post_init__(self) -> None:
        if min(self.context_length, self.prediction_length, self.cadence_minutes, self.stride) < 1:
            raise ValueError("window settings must be positive")


@dataclass(frozen=True)
class WindowSet:
    """Materialized windows and auditable rejection counts for one fixed split."""

    split: SplitName
    context: np.ndarray
    target: np.ndarray
    origins: np.ndarray
    candidate_count: int
    rejected_count: int
    rejection_reasons: dict[str, int]

    def __post_init__(self) -> None:
        if self.context.ndim != 2 or self.target.ndim != 2:
            raise ValueError("context and target must be two-dimensional")
        if len(self.context) != len(self.target) or len(self.context) != len(self.origins):
            raise ValueError("window arrays must have the same sample count")


@dataclass(frozen=True)
class TargetScaler:
    """Single-target robust scaler fitted only from training observations."""

    center: float
    scale: float
    fitted_split: str = "train"

    @classmethod
    def fit(cls, values: np.ndarray, *, split: str) -> TargetScaler:
        """Fit median/IQR scaling and reject non-training inputs."""
        if split != "train":
            raise ValueError("target scaler may only be fitted on the training split")
        array = np.asarray(values, dtype=np.float64).reshape(-1)
        finite = array[np.isfinite(array)]
        if finite.size == 0:
            raise ValueError("training values contain no finite observations")
        center = float(np.median(finite))
        q25, q75 = np.quantile(finite, [0.25, 0.75])
        scale = float(q75 - q25)
        if not np.isfinite(scale) or scale <= 1e-12:
            scale = float(np.std(finite))
        if not np.isfinite(scale) or scale <= 1e-12:
            scale = 1.0
        return cls(center=center, scale=scale)

    def transform(self, values: np.ndarray) -> np.ndarray:
        """Scale values without changing missing-value semantics."""
        return ((np.asarray(values, dtype=np.float32) - self.center) / self.scale).astype(
            np.float32
        )

    def inverse_transform(self, values: np.ndarray) -> np.ndarray:
        """Restore physical kW units."""
        return (np.asarray(values, dtype=np.float32) * self.scale + self.center).astype(np.float32)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": "1.0",
            "type": "robust_iqr",
            "center": self.center,
            "scale": self.scale,
            "fitted_split": self.fitted_split,
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> TargetScaler:
        if value.get("fitted_split") != "train":
            raise ValueError("saved scaler was not fitted on the training split")
        center = value["center"]
        scale = value["scale"]
        if not isinstance(center, int | float) or not isinstance(scale, int | float):
            raise ValueError("saved scaler center and scale must be numeric")
        return cls(center=float(center), scale=float(scale))


@dataclass(frozen=True)
class ForecastMetrics:
    """Point forecast metrics in original kW units."""

    mae: float
    rmse: float
    wape: float
    smape: float
    r2: float

    def to_dict(self) -> dict[str, float]:
        return {
            "mae": self.mae,
            "rmse": self.rmse,
            "wape": self.wape,
            "smape": self.smape,
            "r2": self.r2,
        }


def build_windows(frame: pd.DataFrame, *, split: SplitName, config: WindowConfig) -> WindowSet:
    """Build fixed-split windows, rejecting missing, long-gap, and discontinuous samples."""
    required = {"timestamp", "global_active_power_kw", "long_gap", "split"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"processed data is missing window columns: {sorted(missing)}")
    selected = frame.loc[frame["split"].eq(split), list(required)].copy()
    selected = selected.sort_values("timestamp", kind="stable").reset_index(drop=True)
    if selected.empty:
        return _empty_window_set(split, config)

    timestamps = pd.to_datetime(selected["timestamp"]).to_numpy(dtype="datetime64[ns]")
    values = selected["global_active_power_kw"].to_numpy(dtype=np.float64)
    long_gap = selected["long_gap"].fillna(True).to_numpy(dtype=bool)
    total_length = config.context_length + config.prediction_length
    max_origin = len(selected) - config.prediction_length
    origins = range(config.context_length, max_origin + 1, config.stride)
    expected_delta = np.timedelta64(config.cadence_minutes, "m")
    contexts: list[np.ndarray] = []
    targets: list[np.ndarray] = []
    accepted_origins: list[np.datetime64] = []
    reasons = {"missing_or_long_gap": 0, "discontinuous_time": 0}
    candidate_count = 0

    for origin in origins:
        candidate_count += 1
        start = origin - config.context_length
        end = origin + config.prediction_length
        window_values = values[start:end]
        if len(window_values) != total_length:
            continue
        if not np.isfinite(window_values).all() or long_gap[start:end].any():
            reasons["missing_or_long_gap"] += 1
            continue
        window_timestamps = timestamps[start:end]
        if not np.all(np.diff(window_timestamps) == expected_delta):
            reasons["discontinuous_time"] += 1
            continue
        contexts.append(window_values[: config.context_length].astype(np.float32, copy=True))
        targets.append(window_values[config.context_length :].astype(np.float32, copy=True))
        accepted_origins.append(timestamps[origin])

    context_array = np.stack(contexts) if contexts else np.empty((0, config.context_length))
    target_array = np.stack(targets) if targets else np.empty((0, config.prediction_length))
    return WindowSet(
        split=split,
        context=context_array.astype(np.float32, copy=False),
        target=target_array.astype(np.float32, copy=False),
        origins=np.asarray(accepted_origins, dtype="datetime64[ns]"),
        candidate_count=candidate_count,
        rejected_count=candidate_count - len(context_array),
        rejection_reasons=reasons,
    )


def _empty_window_set(split: SplitName, config: WindowConfig) -> WindowSet:
    return WindowSet(
        split=split,
        context=np.empty((0, config.context_length), dtype=np.float32),
        target=np.empty((0, config.prediction_length), dtype=np.float32),
        origins=np.empty(0, dtype="datetime64[ns]"),
        candidate_count=0,
        rejected_count=0,
        rejection_reasons={"missing_or_long_gap": 0, "discontinuous_time": 0},
    )


def naive_predict(
    context: np.ndarray, model: NaiveModelName, *, prediction_length: int
) -> np.ndarray:
    """Predict with persistence, previous-day, or previous-week seasonal values."""
    values = np.asarray(context, dtype=np.float32)
    if values.ndim != 2 or values.shape[1] < 672 or prediction_length != 96:
        raise ValueError("formal naive baselines require batch x 672 context and 96 outputs")
    if not np.isfinite(values).all():
        raise ValueError("naive baseline context must be fully observed")
    if model == "last_value":
        return np.repeat(values[:, -1:], prediction_length, axis=1)
    if model == "seasonal_day":
        return values[:, -prediction_length:].copy()
    if model == "seasonal_week":
        return values[:, :prediction_length].copy()
    raise ValueError(f"unknown naive model: {model}")


def compute_forecast_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> ForecastMetrics:
    """Compute MAE, RMSE, WAPE, sMAPE, and R2 on matching finite arrays."""
    true, pred = _validated_pair(y_true, y_pred)
    error = pred - true
    absolute_error = np.abs(error)
    mae = float(np.mean(absolute_error))
    rmse = float(np.sqrt(np.mean(np.square(error))))
    true_abs_sum = float(np.sum(np.abs(true)))
    wape = float(np.sum(absolute_error) / true_abs_sum) if true_abs_sum > 1e-12 else 0.0
    denominator = np.abs(true) + np.abs(pred)
    smape = float(np.mean(2.0 * absolute_error / np.maximum(denominator, 1e-8)))
    centered = true - np.mean(true)
    total = float(np.sum(np.square(centered)))
    r2 = float(1.0 - np.sum(np.square(error)) / total) if total > 1e-12 else 0.0
    return ForecastMetrics(mae=mae, rmse=rmse, wape=wape, smape=smape, r2=r2)


def compute_step_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> list[dict[str, float | int]]:
    """Return MAE and RMSE for every forecast step."""
    true, pred = _validated_pair(y_true, y_pred, require_two_dimensions=True)
    rows: list[dict[str, float | int]] = []
    for index in range(true.shape[1]):
        error = pred[:, index] - true[:, index]
        rows.append(
            {
                "step": index + 1,
                "minutes": (index + 1) * 15,
                "mae": float(np.mean(np.abs(error))),
                "rmse": float(np.sqrt(np.mean(np.square(error)))),
            }
        )
    return rows


def compute_horizon_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, dict[str, float]]:
    """Return cumulative errors through 1, 6, 12, and 24 hours."""
    true, pred = _validated_pair(y_true, y_pred, require_two_dimensions=True)
    horizons = {"1h": 4, "6h": 24, "12h": 48, "24h": 96}
    if true.shape[1] < max(horizons.values()):
        raise ValueError("formal horizon metrics require 96 prediction points")
    return {
        label: compute_forecast_metrics(true[:, :steps], pred[:, :steps]).to_dict()
        for label, steps in horizons.items()
    }


def calibrate_conformal(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    *,
    interval_level: float = 0.9,
) -> np.ndarray:
    """Calibrate finite-sample corrected absolute-residual quantiles per horizon."""
    if not 0.0 < interval_level < 1.0:
        raise ValueError("interval_level must be between zero and one")
    true, pred = _validated_pair(y_true, y_pred, require_two_dimensions=True)
    residuals = np.abs(true - pred)
    sample_count = residuals.shape[0]
    if sample_count < 2:
        raise ValueError("at least two validation windows are required for conformal calibration")
    quantile_level = min(1.0, np.ceil((sample_count + 1) * interval_level) / sample_count)
    return np.asarray(
        np.quantile(residuals, quantile_level, axis=0, method="higher"),
        dtype=np.float32,
    )


def interval_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    quantiles: np.ndarray,
) -> dict[str, object]:
    """Evaluate clipped non-negative symmetric intervals and per-step coverage."""
    true, pred = _validated_pair(y_true, y_pred, require_two_dimensions=True)
    q = np.asarray(quantiles, dtype=np.float32).reshape(1, -1)
    if q.shape[1] != true.shape[1] or not np.isfinite(q).all() or (q < 0).any():
        raise ValueError("conformal quantiles must match the prediction horizon")
    lower = np.maximum(0.0, pred - q)
    upper = pred + q
    covered = (true >= lower) & (true <= upper)
    width = upper - lower
    return {
        "coverage": float(np.mean(covered)),
        "average_width_kw": float(np.mean(width)),
        "step_coverage": np.mean(covered, axis=0).astype(float).tolist(),
        "step_average_width_kw": np.mean(width, axis=0).astype(float).tolist(),
    }


def _validated_pair(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    *,
    require_two_dimensions: bool = False,
) -> tuple[np.ndarray, np.ndarray]:
    true = np.asarray(y_true, dtype=np.float64)
    pred = np.asarray(y_pred, dtype=np.float64)
    if true.shape != pred.shape or true.size == 0:
        raise ValueError("truth and prediction arrays must be non-empty with matching shape")
    if require_two_dimensions and true.ndim != 2:
        raise ValueError("metric requires window x horizon arrays")
    if not np.isfinite(true).all() or not np.isfinite(pred).all():
        raise ValueError("metrics require finite truth and predictions")
    return true, pred
