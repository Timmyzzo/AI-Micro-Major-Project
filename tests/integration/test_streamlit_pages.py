"""Cross-page AppTest coverage for the M2.5 presentation refactor."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

import powerinsight.services.advice_service as advice_service_module
from powerinsight.data.catalog import compute_sha256
from powerinsight.services.advice_service import AdviceResult, LlmProbeResult
from powerinsight.services.data_service import DataService
from powerinsight.services.runtime import RuntimeContext
from tests.data.fixtures import raw_minute_frame
from tests.data.runtime import make_runtime_context

PAGE_NAMES = (
    "home",
    "data_center",
    "analytics",
    "forecasting",
    "alerts",
    "reports",
    "settings",
)


@pytest.fixture(scope="module")
def ready_context(tmp_path_factory: pytest.TempPathFactory) -> RuntimeContext:
    root = tmp_path_factory.mktemp("streamlit-pages")
    context = make_runtime_context(root)
    context.paths.builtin_csv.parent.mkdir(parents=True, exist_ok=True)
    raw_minute_frame(pd.date_range("2007-01-01", periods=90, freq="1min")).to_csv(
        context.paths.builtin_csv,
        index=False,
    )
    DataService(
        context,
        expected_sha256=compute_sha256(context.paths.builtin_csv),
    ).prepare_builtin()
    return context


def _run_page(page_name: str, context: RuntimeContext) -> AppTest:
    app = AppTest.from_file(Path("app") / "pages" / f"{page_name}.py")
    app.session_state["runtime_context"] = context
    return app.run(timeout=30)


def test_all_seven_pages_execute_without_exception(ready_context: RuntimeContext) -> None:
    for page_name in PAGE_NAMES:
        app = _run_page(page_name, ready_context)
        assert not app.exception, page_name


def test_advice_page_keeps_external_api_action_visible_without_api_key(
    ready_context: RuntimeContext,
) -> None:
    app = _run_page("reports", ready_context)
    visible_markup = "\n".join(item.value for item in app.markdown)

    assert not app.exception
    assert "智能建议" in visible_markup
    assert "仅供课程演示" not in visible_markup
    assert len(app.metric) == 4
    assert {button.label for button in app.button} == {"生成智能建议"}


def test_advice_page_exports_generated_result_as_markdown(
    ready_context: RuntimeContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        advice_service_module,
        "generate_advice",
        lambda snapshot, settings: AdviceResult("详细建议内容", "api"),
    )

    app = _run_page("reports", ready_context)
    app = app.button[0].click().run(timeout=30)

    assert not app.exception
    assert "详细建议内容" in "\n".join(item.value for item in app.markdown)
    assert len(app.get("download_button")) == 1
    assert app.get("download_button")[0].label == "一键导出建议（Markdown）"


def test_home_shows_presentation_status_and_api_probe(
    ready_context: RuntimeContext,
) -> None:
    app = _run_page("home", ready_context)
    visible_markup = "\n".join(item.value for item in app.markdown)

    assert "系统总览" in visible_markup
    assert "大模型 API" in visible_markup
    assert "推荐展示顺序" in visible_markup
    assert all(token not in visible_markup for token in ("M2", "M3", "M4", "M5"))
    assert {button.label for button in app.button} == {"测试 API 连接"}


def test_home_api_probe_shows_model_response(
    ready_context: RuntimeContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        advice_service_module,
        "probe_llm_connection",
        lambda settings: LlmProbeResult(
            status="success",
            model=settings.openai_model or "test-model",
            text="连接正常",
            latency_ms=42.0,
        ),
    )

    app = _run_page("home", ready_context)
    app = app.button[0].click().run(timeout=30)
    visible_markup = "\n".join(item.value for item in app.markdown)

    assert not app.exception
    assert "连接正常" in visible_markup
    assert app.success
    assert "模型回复：连接正常" in app.success[0].value


def test_analytics_page_uses_real_fixture_metrics_and_charts(
    ready_context: RuntimeContext,
) -> None:
    app = _run_page("analytics", ready_context)
    visible_markup = "\n".join(item.value for item in app.markdown)

    assert not app.exception
    assert "用电分析" in visible_markup
    assert "没有训练模型，也没有预测未来" not in visible_markup
    assert "累计有功电量" in {metric.label for metric in app.metric}
    assert "平均有功功率" in {metric.label for metric in app.metric}
    assert len(app.get("plotly_chart")) == 5
    assert app.date_input
    assert app.dataframe


def test_settings_groups_diagnostics_without_secret_or_timeseries_echo(
    ready_context: RuntimeContext,
) -> None:
    app = _run_page("settings", ready_context)
    visible_markup = "\n".join(item.value for item in app.markdown)

    assert "系统设置" in visible_markup
    assert "大模型型号" in visible_markup
    assert "安全边界" not in visible_markup
    assert "配置来源" not in visible_markup
    assert not app.table
    assert not app.text_input
