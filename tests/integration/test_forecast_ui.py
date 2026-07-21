"""Streamlit AppTest coverage for M4 blocked, ready, cached, and failed states."""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

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
    assert "M2 预测数据依赖不可用" in visible
    assert "页面不训练" in visible
    assert not app.button
    assert not app.get("plotly_chart")


def test_forecast_ui_ready_state_shows_controls_card_and_comparison(tmp_path: Path) -> None:
    context = make_runtime_context(tmp_path)
    prepare_forecast_fixture(context)
    app = _run(context)
    visible = "\n".join(item.value for item in app.markdown)

    assert not app.exception
    assert "M4 模型与固定测试起点可用" in visible
    assert "等待运行即时预测或加载缓存" in visible
    assert len(app.selectbox) == 4
    assert len(app.checkbox) == 1
    assert len(app.button) == 1
    assert len(app.metric) == 4
    assert len(app.dataframe) == 1
    assert not app.get("plotly_chart")


def test_forecast_ui_runs_immediate_then_cached_prediction(tmp_path: Path) -> None:
    context = make_runtime_context(tmp_path)
    prepare_forecast_fixture(context)
    app = _run(context)

    app = app.button[0].click().run(timeout=30)
    visible = "\n".join(item.value for item in app.markdown)
    assert not app.exception
    assert "即时预测完成" in visible
    assert len(app.get("plotly_chart")) == 2
    assert len(app.metric) == 11
    assert len(app.dataframe) == 2
    assert len(app.get("download_button")) == 1

    app = app.button[0].click().run(timeout=30)
    visible = "\n".join(item.value for item in app.markdown)
    assert "已加载离线缓存" in visible


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
    assert "FCST_TEST_FAILURE" in visible
    assert not app.get("plotly_chart")
