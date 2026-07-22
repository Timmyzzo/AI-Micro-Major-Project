"""M4 registry compatibility, inference, cache, export, and persistence tests."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

import pytest

from powerinsight.services.forecast_service import (
    ForecastError,
    ForecastService,
    presentation_model_name,
)
from tests.data.forecasting import prepare_forecast_fixture
from tests.data.runtime import make_runtime_context


def test_forecast_availability_blocks_without_registered_model(tmp_path: Path) -> None:
    context = make_runtime_context(tmp_path)
    availability = ForecastService(context).inspect_availability()

    assert availability.status == "blocked"
    assert availability.title == "预测数据尚未准备"


def test_forecast_availability_lists_compatible_default_and_origins(tmp_path: Path) -> None:
    context = make_runtime_context(tmp_path)
    model = prepare_forecast_fixture(context)
    availability = ForecastService(context).inspect_availability()

    assert availability.status == "ready"
    assert availability.models == (model,)
    assert presentation_model_name(model) == "昨日同刻基线"
    assert len(availability.origins) == 2
    assert availability.origins[0] == datetime(2007, 6, 8)
    comparison = ForecastService(context).comparison_frame(availability.models)
    assert tuple(comparison.columns) == (
        "模型",
        "MAE 平均绝对误差（kW）",
        "RMSE 均方根误差（kW）",
        "R² 决定系数",
    )


def test_naive_forecast_runs_without_scaler_then_reuses_offline_cache(tmp_path: Path) -> None:
    context = make_runtime_context(tmp_path)
    model = prepare_forecast_fixture(context)
    (context.paths.root / model.scaler_path_alias).unlink()
    service = ForecastService(context)
    start = service.inspect_availability().origins[0]

    immediate = service.predict(
        model_id=model.model_id,
        forecast_start=start,
        requested_device="auto",
        allow_cache=True,
    )
    cached = service.predict(
        model_id=model.model_id,
        forecast_start=start,
        requested_device="auto",
        allow_cache=True,
    )

    assert immediate.status == "completed"
    assert cached.status == "cached"
    assert immediate.forecast_id == cached.forecast_id
    assert len(immediate.context) == 672
    assert len(immediate.forecast) == 96
    assert immediate.forecast["is_outside_interval"].sum() == 0


def test_forecast_export_contains_complete_metadata(tmp_path: Path) -> None:
    context = make_runtime_context(tmp_path)
    model = prepare_forecast_fixture(context)
    service = ForecastService(context)
    result = service.predict(
        model_id=model.model_id,
        forecast_start=service.inspect_availability().origins[0],
        requested_device="cpu",
        allow_cache=False,
    )
    exported = result.export_frame()

    assert len(exported) == 96
    assert exported["model_id"].nunique() == 1
    assert exported["preprocess_id"].iat[0] == model.preprocess_id
    assert exported["config_fingerprint"].iat[0] == model.config_fingerprint
    assert exported["interval_level"].iat[0] == 0.9


def test_forecast_rejects_unlisted_start(tmp_path: Path) -> None:
    context = make_runtime_context(tmp_path)
    model = prepare_forecast_fixture(context)
    with pytest.raises(ForecastError, match="日级非重叠") as captured:
        ForecastService(context).predict(
            model_id=model.model_id,
            forecast_start=datetime(2007, 6, 2),
            requested_device="cpu",
            allow_cache=False,
        )
    assert captured.value.code == "FCST_INSUFFICIENT_HISTORY"


def test_scaler_loader_rejects_tampered_hash(tmp_path: Path) -> None:
    context = make_runtime_context(tmp_path)
    model = prepare_forecast_fixture(context)
    scaler_path = context.paths.root / model.scaler_path_alias
    scaler_path.write_text(json.dumps({"fitted_split": "train", "center": 0, "scale": 1}))
    service = ForecastService(context)

    with pytest.raises(ForecastError) as captured:
        service._load_scaler(model)
    assert captured.value.code == "MODEL_SCALER_MISMATCH"


def test_forecast_registers_only_lightweight_sqlite_metadata(tmp_path: Path) -> None:
    context = make_runtime_context(tmp_path)
    model = prepare_forecast_fixture(context)
    service = ForecastService(context)
    result = service.predict(
        model_id=model.model_id,
        forecast_start=service.inspect_availability().origins[0],
        requested_device="cpu",
        allow_cache=False,
    )
    connection = sqlite3.connect(context.paths.database_path)
    try:
        row = connection.execute(
            "SELECT forecast_id, model_id, status, artifact_path_alias FROM forecasts"
        ).fetchone()
        columns = connection.execute("PRAGMA table_info(forecasts)").fetchall()
    finally:
        connection.close()

    assert row == (result.forecast_id, model.model_id, "completed", result.cache_path_alias)
    assert "y_pred_kw" not in {column[1] for column in columns}
