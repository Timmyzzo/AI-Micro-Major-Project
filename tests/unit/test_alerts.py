"""Deterministic M5 alert rule tests."""

from datetime import UTC, datetime

import pandas as pd

from powerinsight.alerts import (
    alerts_to_frame,
    derive_rule_thresholds,
    evaluate_quality_alerts,
    evaluate_residual_alerts,
    evaluate_rule_alerts,
)
from powerinsight.schemas import DataIssue, DataQualityReport


def test_rule_thresholds_use_training_frame_and_repeat_exactly() -> None:
    frame = pd.DataFrame({"global_active_power_kw": [1.0, 1.1, 0.9, 1.0, 1.2] * 20})
    assert derive_rule_thresholds(frame) == derive_rule_thresholds(frame.copy())


def test_quality_issue_becomes_traceable_alert() -> None:
    generated = datetime(2026, 1, 1, tzinfo=UTC)
    report = DataQualityReport(
        dataset_id="ds_test",
        validation_version="1.0",
        status="attention",
        score=90.0,
        row_count=10,
        parsed_timestamp_count=10,
        duplicate_count=0,
        cadence_violations=0,
        missing_cells_by_column={"load": 2},
        measurement_missing_row_count=2,
        missing_blocks=(),
        issues=(
            DataIssue(
                code="MISSING_VALUE",
                severity="warning",
                message="存在缺失值",
                count=2,
                suggested_action="复核缺失区段",
            ),
        ),
        generated_at=generated,
    )
    alerts = evaluate_quality_alerts(report, dataset_id="ds_test", created_at=generated)
    assert len(alerts) == 1
    assert alerts[0].alert_type == "data_quality"
    assert alerts[0].severity == "attention"


def test_rule_alerts_assign_deterministic_attention_or_critical() -> None:
    training = pd.DataFrame({"global_active_power_kw": [1.0, 1.1, 0.9, 1.0] * 30})
    thresholds = derive_rule_thresholds(training)
    replay = pd.DataFrame(
        {
            "timestamp": pd.date_range("2007-06-01", periods=3, freq="15min"),
            "global_active_power_kw": [1.0, thresholds.load_attention_kw * 1.01, 9.0],
        }
    )
    alerts = evaluate_rule_alerts(
        replay,
        dataset_id="ds_test",
        thresholds=thresholds,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    assert alerts
    assert {item.severity for item in alerts} <= {"attention", "critical"}
    assert alerts == evaluate_rule_alerts(
        replay,
        dataset_id="ds_test",
        thresholds=thresholds,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def test_residual_alerts_ignore_inside_points_and_capture_interval_evidence() -> None:
    forecast = pd.DataFrame(
        {
            "timestamp": pd.date_range("2007-06-01", periods=2, freq="15min"),
            "y_pred_kw": [1.0, 1.0],
            "lower_kw": [0.5, 0.5],
            "upper_kw": [1.5, 1.5],
            "y_true_kw": [1.2, 2.0],
        }
    )
    alerts = evaluate_residual_alerts(
        forecast,
        forecast_id="fcst_test",
        dataset_id="ds_test",
        model_id="mdl_test",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    assert len(alerts) == 1
    assert alerts[0].expected_upper == 1.5
    assert alerts[0].evidence_ids[0] == "fcst_test"


def test_alert_csv_contract_protects_formula_injection() -> None:
    forecast = pd.DataFrame(
        {
            "timestamp": [pd.Timestamp("2007-06-01")],
            "y_pred_kw": [1.0],
            "lower_kw": [0.5],
            "upper_kw": [1.5],
            "y_true_kw": [2.0],
        }
    )
    alert = evaluate_residual_alerts(
        forecast,
        forecast_id="=unsafe",
        dataset_id="ds_test",
        model_id="mdl_test",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )[0]
    exported = alerts_to_frame((alert,))
    assert tuple(exported.columns[:6]) == (
        "alert_id",
        "alert_type",
        "severity",
        "start_time",
        "end_time",
        "metric",
    )
    assert exported["evidence_ids"].iat[0].startswith("'")
