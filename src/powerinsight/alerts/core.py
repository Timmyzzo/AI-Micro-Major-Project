"""Pure, deterministic alert evaluation for quality, rules, and forecast residuals."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Literal

import numpy as np
import pandas as pd  # type: ignore[import-untyped]

from powerinsight.schemas import DataQualityReport

AlertSeverity = Literal["info", "attention", "critical"]
AlertType = Literal["data_quality", "rule", "residual"]
ALERT_RULE_VERSION = "m5-alert-rules-1.0"


@dataclass(frozen=True)
class RuleThresholds:
    """Training-only robust thresholds used by deterministic rule alerts."""

    load_attention_kw: float
    load_critical_kw: float
    change_attention_kw: float
    change_critical_kw: float
    source: str = "training median + MAD"


@dataclass(frozen=True)
class Alert:
    """One auditable alert with stable identity and export fields."""

    alert_id: str
    alert_type: AlertType
    severity: AlertSeverity
    start_time: datetime | None
    end_time: datetime | None
    title: str
    metric: str
    observed_value: float | None
    expected_lower: float | None
    expected_upper: float | None
    threshold: float | None
    score: float
    evidence_ids: tuple[str, ...]
    dataset_id: str
    model_id: str | None
    rule_version: str
    status: Literal["open", "acknowledged", "ignored"] = "open"
    note: str = ""
    created_at: datetime = datetime(1970, 1, 1, tzinfo=UTC)


def derive_rule_thresholds(training_frame: pd.DataFrame) -> RuleThresholds:
    """Derive reproducible load and change thresholds from training data only."""
    values = pd.to_numeric(training_frame["global_active_power_kw"], errors="coerce").dropna()
    if len(values) < 2:
        raise ValueError("training data must contain at least two finite load values")
    changes = values.diff().abs().dropna()
    load_median, load_mad = _median_mad(values.to_numpy(dtype=float))
    change_median, change_mad = _median_mad(changes.to_numpy(dtype=float))
    return RuleThresholds(
        load_attention_kw=max(load_median + 4.0 * load_mad, float(values.quantile(0.99))),
        load_critical_kw=max(load_median + 6.0 * load_mad, float(values.quantile(0.999))),
        change_attention_kw=max(change_median + 4.0 * change_mad, float(changes.quantile(0.99))),
        change_critical_kw=max(change_median + 6.0 * change_mad, float(changes.quantile(0.999))),
    )


def evaluate_quality_alerts(
    report: DataQualityReport, *, dataset_id: str, created_at: datetime
) -> tuple[Alert, ...]:
    """Convert data-quality findings into deterministic alert records."""
    alerts: list[Alert] = []
    severity_map: dict[str, AlertSeverity] = {
        "error": "critical",
        "warning": "attention",
        "information": "info",
    }
    for issue in report.issues:
        alerts.append(
            _alert(
                alert_type="data_quality",
                severity=severity_map[issue.severity],
                start_time=issue.start_time,
                end_time=issue.end_time,
                title=issue.message,
                metric=issue.code,
                observed_value=float(issue.count),
                expected_lower=0.0,
                expected_upper=0.0,
                threshold=0.0,
                score=float(issue.count),
                evidence_ids=(f"quality:{report.validation_version}:{issue.code}",),
                dataset_id=dataset_id,
                model_id=None,
                created_at=created_at,
            )
        )
    return tuple(alerts)


def evaluate_rule_alerts(
    frame: pd.DataFrame,
    *,
    dataset_id: str,
    thresholds: RuleThresholds,
    created_at: datetime,
) -> tuple[Alert, ...]:
    """Evaluate high-load and abrupt-change rules over one ordered replay frame."""
    ordered = frame.sort_values("timestamp", kind="stable").reset_index(drop=True).copy()
    ordered["load"] = pd.to_numeric(ordered["global_active_power_kw"], errors="coerce")
    ordered["change"] = ordered["load"].diff().abs()
    alerts: list[Alert] = []
    for row in ordered.itertuples(index=False):
        timestamp = pd.Timestamp(row.timestamp).to_pydatetime()
        if pd.notna(row.load) and row.load > thresholds.load_attention_kw:
            critical = row.load > thresholds.load_critical_kw
            threshold = thresholds.load_critical_kw if critical else thresholds.load_attention_kw
            alerts.append(
                _alert(
                    alert_type="rule",
                    severity="critical" if critical else "attention",
                    start_time=timestamp,
                    end_time=timestamp,
                    title="总有功功率超过训练段稳健阈值",
                    metric="global_active_power_kw",
                    observed_value=float(row.load),
                    expected_lower=0.0,
                    expected_upper=threshold,
                    threshold=threshold,
                    score=float(row.load / threshold),
                    evidence_ids=(f"rule:load:{ALERT_RULE_VERSION}",),
                    dataset_id=dataset_id,
                    model_id=None,
                    created_at=created_at,
                )
            )
        if pd.notna(row.change) and row.change > thresholds.change_attention_kw:
            critical = row.change > thresholds.change_critical_kw
            threshold = (
                thresholds.change_critical_kw if critical else thresholds.change_attention_kw
            )
            alerts.append(
                _alert(
                    alert_type="rule",
                    severity="critical" if critical else "attention",
                    start_time=timestamp,
                    end_time=timestamp,
                    title="相邻 15 分钟负荷变化超过训练段稳健阈值",
                    metric="absolute_load_change_kw",
                    observed_value=float(row.change),
                    expected_lower=0.0,
                    expected_upper=threshold,
                    threshold=threshold,
                    score=float(row.change / threshold),
                    evidence_ids=(f"rule:change:{ALERT_RULE_VERSION}",),
                    dataset_id=dataset_id,
                    model_id=None,
                    created_at=created_at,
                )
            )
    return tuple(alerts)


def evaluate_residual_alerts(
    forecast: pd.DataFrame,
    *,
    forecast_id: str,
    dataset_id: str,
    model_id: str,
    created_at: datetime,
) -> tuple[Alert, ...]:
    """Create alerts only where observed values fall outside forecast intervals."""
    alerts: list[Alert] = []
    for row in forecast.itertuples(index=False):
        observed = float(row.y_true_kw)
        lower = float(row.lower_kw)
        upper = float(row.upper_kw)
        if lower <= observed <= upper:
            continue
        width = max(upper - lower, 1e-9)
        residual = observed - float(row.y_pred_kw)
        distance = lower - observed if observed < lower else observed - upper
        score = 1.0 + distance / width
        severity: AlertSeverity = "critical" if score >= 1.5 else "attention"
        timestamp = pd.Timestamp(row.timestamp).to_pydatetime()
        alerts.append(
            _alert(
                alert_type="residual",
                severity=severity,
                start_time=timestamp,
                end_time=timestamp,
                title="真实负荷落在预测区间之外",
                metric="forecast_residual_kw",
                observed_value=observed,
                expected_lower=lower,
                expected_upper=upper,
                threshold=width,
                score=score,
                evidence_ids=(forecast_id, f"residual:{timestamp.isoformat()}"),
                dataset_id=dataset_id,
                model_id=model_id,
                created_at=created_at,
                extra_identity={"residual": residual},
            )
        )
    return tuple(alerts)


def alerts_to_frame(alerts: tuple[Alert, ...]) -> pd.DataFrame:
    """Return the stable alert CSV contract with formula-injection protection."""
    columns = (
        "alert_id",
        "alert_type",
        "severity",
        "start_time",
        "end_time",
        "metric",
        "observed_value",
        "expected_lower",
        "expected_upper",
        "threshold",
        "score",
        "status",
        "dataset_id",
        "model_id",
        "rule_version",
        "evidence_ids",
        "title",
        "note",
        "created_at",
    )
    records: list[dict[str, object]] = []
    for alert in alerts:
        record = asdict(alert)
        record["evidence_ids"] = "|".join(alert.evidence_ids)
        for key, value in tuple(record.items()):
            if isinstance(value, datetime):
                record[key] = value.isoformat()
            elif isinstance(value, str):
                record[key] = _safe_csv_text(value)
        records.append(record)
    return pd.DataFrame.from_records(records, columns=columns)


def _alert(*, extra_identity: dict[str, object] | None = None, **values: object) -> Alert:
    identity = {**values, **(extra_identity or {})}
    identity.pop("created_at", None)
    digest = hashlib.sha256(
        json.dumps(identity, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()[:16]
    return Alert(alert_id=f"alt_{digest}", rule_version=ALERT_RULE_VERSION, **values)  # type: ignore[arg-type]


def _median_mad(values: np.ndarray) -> tuple[float, float]:
    median = float(np.median(values))
    mad = float(np.median(np.abs(values - median))) * 1.4826
    return median, max(mad, 1e-9)


def _safe_csv_text(value: str) -> str:
    return f"'{value}" if value.startswith(("=", "+", "-", "@")) else value
