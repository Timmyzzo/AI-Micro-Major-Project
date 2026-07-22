"""Streamlit AppTest coverage for M3 ready, attention, empty, and failure states."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

import powerinsight.services.analytics_service as analytics_module
from powerinsight.data.catalog import compute_sha256
from powerinsight.services.analytics_service import AnalyticsError, AnalyticsService
from powerinsight.services.data_service import DataService
from powerinsight.services.runtime import RuntimeContext
from tests.data.fixtures import raw_minute_frame
from tests.data.runtime import make_runtime_context


def _context_with_day(root: Path, *, missing_positions: set[int] | None = None) -> RuntimeContext:
    context = make_runtime_context(root)
    context.paths.builtin_csv.parent.mkdir(parents=True, exist_ok=True)
    raw_minute_frame(
        pd.date_range("2007-01-01", periods=24 * 60, freq="1min"),
        missing_positions=missing_positions,
    ).to_csv(context.paths.builtin_csv, index=False)
    DataService(
        context,
        expected_sha256=compute_sha256(context.paths.builtin_csv),
    ).prepare_builtin()
    return context


def _run(context: RuntimeContext) -> AppTest:
    app = AppTest.from_file("app/pages/analytics.py")
    app.session_state["runtime_context"] = context
    return app.run(timeout=30)


def test_analytics_ready_state_has_real_metrics_charts_and_date_control(tmp_path: Path) -> None:
    app = _run(_context_with_day(tmp_path))
    visible_markup = "\n".join(item.value for item in app.markdown)

    assert not app.exception
    assert "用电分析" in visible_markup
    assert "M3" not in visible_markup
    assert "不训练模型" not in visible_markup
    assert len(app.date_input) == 1
    assert len(app.metric) == 8
    assert len(app.get("plotly_chart")) == 5
    assert app.dataframe
    assert not app.button


def test_analytics_attention_state_preserves_long_gap_evidence(tmp_path: Path) -> None:
    app = _run(_context_with_day(tmp_path, missing_positions=set(range(300, 361))))

    assert not app.exception
    assert app.warning
    assert "缺失区段" in app.warning[0].value
    assert len(app.get("plotly_chart")) == 5


def test_analytics_empty_state_does_not_show_zero_kpis_or_charts(tmp_path: Path) -> None:
    context = _context_with_day(tmp_path)
    state = DataService(context).inspect_builtin_state()
    assert state.manifest is not None
    processed_path = (
        context.paths.data_dir / "processed" / state.manifest.preprocess_id / "power_15min.parquet"
    )
    frame = pd.read_parquet(processed_path)
    for column in (
        "global_active_power_kw",
        "global_active_energy_wh",
        "sub_metering_1_wh",
        "sub_metering_2_wh",
        "sub_metering_3_wh",
        "unmetered_energy_wh",
    ):
        frame[column] = float("nan")
    frame.to_parquet(processed_path, index=False)
    analytics_module.clear_analytics_cache()

    app = _run(context)
    visible_markup = "\n".join(item.value for item in app.markdown)

    assert not app.exception
    assert "没有有效负荷数据" in visible_markup
    assert "不会把空范围或全缺失范围显示成 0" in visible_markup
    assert not app.metric
    assert not app.get("plotly_chart")


def test_analytics_blocked_state_explains_missing_manifest(tmp_path: Path) -> None:
    context = make_runtime_context(tmp_path)
    context.paths.builtin_csv.parent.mkdir(parents=True, exist_ok=True)
    raw_minute_frame(pd.date_range("2007-01-01", periods=30, freq="1min")).to_csv(
        context.paths.builtin_csv,
        index=False,
    )

    app = _run(context)
    visible_markup = "\n".join(item.value for item in app.markdown)

    assert not app.exception
    assert "分析数据尚未准备" in visible_markup
    assert "ANALYTICS_MANIFEST_MISSING" not in visible_markup
    assert not app.metric
    assert not app.get("plotly_chart")


def test_analytics_failed_state_is_display_safe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context_with_day(tmp_path)

    class FailingAnalyticsService(AnalyticsService):
        def analyze(self, *, start: datetime, end_exclusive: datetime) -> object:
            del start, end_exclusive
            raise AnalyticsError(
                code="ANALYTICS_TEST_FAILURE",
                title="用电分析执行失败",
                reason="测试夹具触发确定性失败。",
                evidence=("fixture",),
                next_step="检查夹具。",
            )

    monkeypatch.setattr(analytics_module, "AnalyticsService", FailingAnalyticsService)
    app = _run(context)
    visible_markup = "\n".join(item.value for item in app.markdown)

    assert not app.exception
    assert "用电分析执行失败" in visible_markup
    assert "ANALYTICS_TEST_FAILURE" not in visible_markup
    assert str(tmp_path) not in visible_markup
    assert not app.metric
    assert not app.get("plotly_chart")
