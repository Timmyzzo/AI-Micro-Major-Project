"""Streamlit AppTest coverage for M5 replay and deterministic alerts."""

from pathlib import Path

from streamlit.testing.v1 import AppTest

from powerinsight.services.runtime import RuntimeContext
from tests.data.forecasting import prepare_forecast_fixture
from tests.data.runtime import make_runtime_context


def _run(context: RuntimeContext) -> AppTest:
    app = AppTest.from_file("app/pages/alerts.py")
    app.session_state["runtime_context"] = context
    return app.run(timeout=30)


def test_alert_ui_blocks_without_verified_forecast_dependencies(tmp_path: Path) -> None:
    app = _run(make_runtime_context(tmp_path))
    visible = "\n".join(item.value for item in app.markdown)

    assert not app.exception
    assert "M2 预测数据依赖不可用" in visible
    assert "统计异常不等于电气故障" in app.warning[0].value
    assert not app.get("plotly_chart")


def test_alert_ui_loads_read_only_replay_controls_and_export(tmp_path: Path) -> None:
    context = make_runtime_context(tmp_path)
    prepare_forecast_fixture(context)
    app = _run(context)

    app = app.button[0].click().run(timeout=30)
    assert not app.exception
    assert "训练段稳健阈值" in "\n".join(item.value for item in app.caption)
    assert {button.label for button in app.button} >= {"继续", "暂停", "单步", "重置"}
    assert len(app.get("plotly_chart")) == 1
    assert len(app.metric) == 4
    assert len(app.get("download_button")) == 1
