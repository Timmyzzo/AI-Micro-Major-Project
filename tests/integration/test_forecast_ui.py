"""Streamlit AppTest coverage for M4 blocked, ready, cached, and failed states."""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from powerinsight.forecasting.registry import RegisteredModel
from powerinsight.services.forecast_service import ForecastError, ForecastService
from powerinsight.services.runtime import RuntimeContext
from tests.data.forecasting import prepare_forecast_fixture
from tests.data.runtime import make_runtime_context


def _run(context: RuntimeContext) -> AppTest:
    app = AppTest.from_file("app/pages/forecasting.py")
    app.session_state["runtime_context"] = context
    return app.run(timeout=30)


def test_forecast_ui_blocked_state_does_not_train_or_draw(tmp_path: Path) -> None:
    app = _run(make_runtime_context(tmp_path))
    visible = "\n".join(item.value for item in app.markdown)

    assert not app.exception
    assert "预测数据尚未准备" in visible
    assert "M2" not in visible
    assert not app.button
    assert not app.get("plotly_chart")


def test_forecast_ui_ready_state_shows_controls_card_and_comparison(tmp_path: Path) -> None:
    context = make_runtime_context(tmp_path)
    prepare_forecast_fixture(context)
    app = _run(context)
    visible = "\n".join(item.value for item in app.markdown)

    assert not app.exception
    assert "开始预测" in visible
    assert "当前模型" in visible
    assert "模型对比" in visible
    assert len(app.selectbox) == 2
    assert len(app.checkbox) == 0
    assert len(app.button) == 1
    assert len(app.metric) == 3
    assert len(app.dataframe) == 1
    assert not app.get("plotly_chart")


def test_forecast_ui_shows_collapsible_training_history(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = make_runtime_context(tmp_path)
    prepare_forecast_fixture(context)
    original_load_metrics = ForecastService.load_metrics

    def load_metrics_with_history(
        self: ForecastService,
        model: RegisteredModel,
    ) -> dict[str, object]:
        metrics = original_load_metrics(self, model)
        metrics["training_history"] = [
            {"epoch": 1, "train_loss": 0.5, "validation_mae": 0.7},
            {"epoch": 2, "train_loss": 0.4, "validation_mae": 0.8},
        ]
        return metrics

    monkeypatch.setattr(ForecastService, "load_metrics", load_metrics_with_history)
    app = _run(context)

    assert not app.exception
    assert app.expander[0].label == "查看模型训练过程"
    assert len(app.dataframe) == 2


def test_forecast_ui_runs_immediate_then_cached_prediction(tmp_path: Path) -> None:
    context = make_runtime_context(tmp_path)
    prepare_forecast_fixture(context)
    app = _run(context)

    app = app.button[0].click().run(timeout=30)
    assert not app.exception
    assert app.success
    assert "预测完成" in app.success[0].value
    assert len(app.get("plotly_chart")) == 2
    assert len(app.metric) == 10
    assert len(app.dataframe) == 2
    assert len(app.get("download_button")) == 1

    app = app.button[0].click().run(timeout=30)
    assert app.success
    assert "预测完成" in app.success[0].value


def test_forecast_ui_failed_state_is_explicit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = make_runtime_context(tmp_path)
    prepare_forecast_fixture(context)

    def fail_predict(self: ForecastService, **_: object) -> object:
        raise ForecastError(
            code="FCST_TEST_FAILURE",
            title="预测执行失败",
            reason="测试夹具触发失败。",
            evidence=("fixture",),
            next_step="检查夹具。",
        )

    monkeypatch.setattr(ForecastService, "predict", fail_predict)
    app = _run(context)
    app = app.button[0].click().run(timeout=30)
    visible = "\n".join(item.value for item in app.markdown)

    assert not app.exception
    assert "预测执行失败" in visible
    assert "FCST_TEST_FAILURE" not in visible
    assert not app.get("plotly_chart")
