"""Streamlit navigation import and default-page smoke tests."""

from __future__ import annotations

import importlib

from streamlit.testing.v1 import AppTest

from powerinsight.config import ENVIRONMENT_FIELDS


def test_streamlit_entry_imports_with_simplified_pages() -> None:
    module = importlib.import_module("app.streamlit_app")

    assert len(module.PAGE_SPECS) == 7
    assert tuple(spec[1] for spec in module.PAGE_SPECS) == (
        "首页总览",
        "数据中心",
        "用电分析",
        "负荷预测",
        "监测预警",
        "智能建议",
        "系统设置",
    )
    assert all(spec[2].startswith(":material/") for spec in module.PAGE_SPECS)


def test_streamlit_default_page_executes_without_exception(monkeypatch: object) -> None:
    for environment_name in ENVIRONMENT_FIELDS:
        monkeypatch.delenv(environment_name, raising=False)  # type: ignore[attr-defined]

    app = AppTest.from_file("app/streamlit_app.py").run(timeout=60)

    assert not app.exception
    assert sum("powerinsight-theme" in item.value for item in app.markdown) == 1
    assert any("智电洞察" in item.value for item in app.sidebar.markdown)
    assert any("M4 · 模型闭环" in item.value for item in app.sidebar.markdown)
    assert any("模型与智能能力" in item.value for item in app.markdown)
    assert not app.warning
