"""Streamlit navigation import and default-page smoke tests."""

from __future__ import annotations

import importlib

from streamlit.testing.v1 import AppTest

from powerinsight.config import ENVIRONMENT_FIELDS


def test_streamlit_entry_imports_with_all_planned_pages() -> None:
    module = importlib.import_module("app.streamlit_app")

    assert len(module.PAGE_SPECS) == 8
    assert tuple(spec[1] for spec in module.PAGE_SPECS) == (
        "首页总览",
        "数据中心",
        "用电分析",
        "负荷预测",
        "监测预警",
        "优化决策",
        "智能报告",
        "系统设置",
    )


def test_streamlit_default_page_executes_without_exception(monkeypatch: object) -> None:
    for environment_name in ENVIRONMENT_FIELDS:
        monkeypatch.delenv(environment_name, raising=False)  # type: ignore[attr-defined]

    app = AppTest.from_file("app/streamlit_app.py").run(timeout=60)

    assert not app.exception
    assert any("尚未进行数据处理和模型训练" in warning.value for warning in app.warning)
