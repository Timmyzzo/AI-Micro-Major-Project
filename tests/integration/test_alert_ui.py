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
    assert "预测数据尚未准备" in visible
    assert not app.warning
    assert not app.get("plotly_chart")


def test_alert_ui_starts_automatic_half_second_playback_and_exports(tmp_path: Path) -> None:
    context = make_runtime_context(tmp_path)
    prepare_forecast_fixture(context)
    app = _run(context)

    app = app.button[0].click().run(timeout=30)
    assert not app.exception
    assert {button.label for button in app.button} == {"一键启动监测"}
    assert any("每 0.5 秒更新一个预测点" in item.value for item in app.info)
    assert app.session_state["replay_running"] is True
    assert not app.slider
    assert len(app.selectbox) == 2
    assert len(app.get("plotly_chart")) == 1
    assert len(app.metric) == 4
    assert len(app.get("download_button")) == 1

    app.session_state["replay_running"] = False
    app.session_state["replay_index"] = 10_000
    app = app.run(timeout=30)

    assert not app.exception
    assert "监测播放已完成" in app.success[0].value
    assert app.slider[0].label == "回看监测时间点"
    assert app.slider[0].value == app.slider[0].max
