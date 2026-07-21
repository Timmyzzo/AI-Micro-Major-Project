"""Streamlit data-center empty and completed-state tests."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from streamlit.testing.v1 import AppTest

from powerinsight.data.catalog import compute_sha256
from powerinsight.services.data_service import DataService
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
    assert any("尚未运行完整质量校验" in item.value for item in app.info)
    assert any("尚未生成可用的 15 分钟处理产物" in item.value for item in app.info)


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
    assert "记录数" in labels
    assert "15 分钟点数" in labels
    assert "训练集" in labels
    assert any("Manifest" in item.value for item in app.markdown)
    assert app.dataframe
