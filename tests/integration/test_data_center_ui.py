"""Streamlit data-center empty and completed-state tests."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

import powerinsight.services.data_service as data_service_module
from powerinsight.data.catalog import compute_sha256
from powerinsight.services.data_service import DataService
from powerinsight.services.runtime import RuntimeContext
from tests.data.fixtures import raw_minute_frame
from tests.data.runtime import make_runtime_context


def _write_source(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw_minute_frame(pd.date_range("2007-01-01", periods=30, freq="1min")).to_csv(
        path,
        index=False,
    )


def test_data_center_renders_true_empty_state(tmp_path: Path) -> None:
    context = make_runtime_context(tmp_path)
    _write_source(context.paths.builtin_csv)
    app = AppTest.from_file("app/pages/data_center.py")
    app.session_state["runtime_context"] = context

    app.run(timeout=30)

    assert not app.exception
    visible = "\n".join(item.value for item in app.markdown)
    assert "分析数据尚未准备" in visible
    assert "UCI Machine Learning Repository" in visible
    assert {button.label for button in app.button} == {"准备分析数据"}


def test_data_center_renders_completed_manifest_and_split_counts(tmp_path: Path) -> None:
    context = make_runtime_context(tmp_path)
    _write_source(context.paths.builtin_csv)
    service = DataService(
        context,
        expected_sha256=compute_sha256(context.paths.builtin_csv),
    )
    service.prepare_builtin()
    app = AppTest.from_file("app/pages/data_center.py")
    app.session_state["runtime_context"] = context

    app.run(timeout=30)

    assert not app.exception
    labels = {metric.label for metric in app.metric}
    assert "原始记录" in labels
    assert "分析数据点" in labels
    assert "有效数据覆盖率" in labels
    assert not app.caption
    assert app.dataframe


def test_data_center_buttons_trigger_validation_and_preprocessing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = make_runtime_context(tmp_path)
    _write_source(context.paths.builtin_csv)
    source_sha256 = compute_sha256(context.paths.builtin_csv)

    class FixtureDataService(DataService):
        def __init__(self, runtime_context: RuntimeContext) -> None:
            super().__init__(runtime_context, expected_sha256=source_sha256)

    monkeypatch.setattr(data_service_module, "DataService", FixtureDataService)
    app = AppTest.from_file("app/pages/data_center.py")
    app.session_state["runtime_context"] = context
    app.run(timeout=30)

    app.button[0].click().run(timeout=30)
    assert not app.exception
    assert any("分析数据已准备完成" in item.value for item in app.success)
    assert "分析数据点" in {metric.label for metric in app.metric}
