"""Alert service over prepared data and forecast results."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import pandas as pd  # type: ignore[import-untyped]

from powerinsight.alerts import (
    Alert,
    RuleThresholds,
    alerts_to_frame,
    derive_rule_thresholds,
    evaluate_quality_alerts,
    evaluate_residual_alerts,
    evaluate_rule_alerts,
)
from powerinsight.services.data_service import DataService
from powerinsight.services.forecast_service import ForecastResult
from powerinsight.services.runtime import RuntimeContext


@dataclass(frozen=True)
class AlertEvaluation:
    """Deterministic alerts and threshold provenance for one forecast replay."""

    alerts: tuple[Alert, ...]
    thresholds: RuleThresholds
    replay_frame: pd.DataFrame

    def export_frame(self) -> pd.DataFrame:
        return alerts_to_frame(self.alerts)


class AlertService:
    """Evaluate quality, training-derived rules, and residuals without external calls."""

    def __init__(self, context: RuntimeContext) -> None:
        self._context = context

    def evaluate(self, result: ForecastResult) -> AlertEvaluation:
        """Evaluate three alert classes against a compatible replay result."""
        state = DataService(self._context).inspect_builtin_state()
        if state.manifest is None or not state.processed_exists:
            raise ValueError("prepared analysis data is required")
        manifest = state.manifest
        processed_path = (
            self._context.paths.data_dir
            / "processed"
            / manifest.preprocess_id
            / "power_15min.parquet"
        )
        frame = pd.read_parquet(
            processed_path, columns=["timestamp", "global_active_power_kw", "split"]
        )
        training = frame.loc[frame["split"] == "train"]
        thresholds = derive_rule_thresholds(training)
        replay = result.forecast.rename(columns={"y_true_kw": "global_active_power_kw"}).copy()
        created_at = datetime.now(UTC)
        quality = evaluate_quality_alerts(
            manifest.quality_report, dataset_id=manifest.dataset_id, created_at=created_at
        )
        rules = evaluate_rule_alerts(
            replay,
            dataset_id=manifest.dataset_id,
            thresholds=thresholds,
            created_at=created_at,
        )
        residuals = evaluate_residual_alerts(
            result.forecast,
            forecast_id=result.forecast_id,
            dataset_id=manifest.dataset_id,
            model_id=result.model.model_id,
            created_at=created_at,
        )
        ordered = tuple(
            sorted(
                (*quality, *rules, *residuals),
                key=lambda item: (item.start_time or datetime.min, item.alert_type, item.alert_id),
            )
        )
        return AlertEvaluation(alerts=ordered, thresholds=thresholds, replay_frame=replay)
