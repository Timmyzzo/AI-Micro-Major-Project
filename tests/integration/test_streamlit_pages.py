"""Cross-page AppTest coverage for the M2.5 presentation refactor."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from powerinsight.data.catalog import compute_sha256
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
    "optimization",
    "reports",
    "settings",
)
PLANNED_PAGE_NAMES = ("alerts", "optimization", "reports")


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


def test_all_eight_pages_execute_without_exception(ready_context: RuntimeContext) -> None:
    for page_name in PAGE_NAMES:
        app = _run_page(page_name, ready_context)
        assert not app.exception, page_name


@pytest.mark.parametrize("page_name", PLANNED_PAGE_NAMES)
def test_planned_pages_remain_honest_and_side_effect_free(
    page_name: str,
    ready_context: RuntimeContext,
) -> None:
    app = _run_page(page_name, ready_context)
    visible_markup = "\n".join(item.value for item in app.markdown)

    assert "M2 数据基础已经具备" in visible_markup
    assert "能力边界已定义，功能尚未实现" in visible_markup
    assert "不自动训练" in visible_markup
    assert "不调用外部 API" in visible_markup
    assert "不生成虚假指标" in visible_markup
    assert not app.metric
    assert not app.button
    assert not app.get("plotly_chart")


def test_home_distinguishes_verified_data_from_untrained_models(
    ready_context: RuntimeContext,
) -> None:
    app = _run_page("home", ready_context)
    visible_markup = "\n".join(item.value for item in app.markdown)

    assert "M2 数据与 M3 分析基础可用" in visible_markup
    assert "已完成 · M3" in visible_markup
    assert "尚未训练任何模型" in visible_markup
    assert "无预测结果" in visible_markup
    assert "耗时操作只由明确动作触发" in visible_markup


def test_analytics_page_uses_real_fixture_metrics_and_charts(
    ready_context: RuntimeContext,
) -> None:
    app = _run_page("analytics", ready_context)
    visible_markup = "\n".join(item.value for item in app.markdown)

    assert not app.exception
    assert "分析完成" in visible_markup
    assert "没有训练模型，也没有预测未来" in visible_markup
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

    assert "只读诊断" in visible_markup
    assert "只存元数据，不存 26 万行原始或聚合时序" in visible_markup
    assert "Key 也不会回显" in visible_markup
    assert not app.table
    assert not app.text_input
