"""PowerInsight Streamlit navigation entrypoint."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from powerinsight.config import ConfigurationError
from powerinsight.services.runtime import initialize_runtime

APP_DIR = Path(__file__).resolve().parent
PAGE_SPECS: tuple[tuple[str, str, str], ...] = (
    ("home.py", "首页总览", "🏠"),
    ("data_center.py", "数据中心", "🗂️"),
    ("analytics.py", "用电分析", "📊"),
    ("forecasting.py", "负荷预测", "📈"),
    ("alerts.py", "监测预警", "⚠️"),
    ("optimization.py", "优化决策", "⚙️"),
    ("reports.py", "智能报告", "📝"),
    ("settings.py", "系统设置", "🔧"),
)


def main() -> None:
    """Initialize the safe runtime and dispatch the selected page."""
    st.set_page_config(
        page_title="智电洞察 PowerInsight",
        page_icon="⚡",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    try:
        context = initialize_runtime()
    except ConfigurationError as exc:
        st.error(f"配置加载失败：{exc}")
        st.stop()

    st.session_state["runtime_context"] = context
    pages = [
        st.Page(
            APP_DIR / "pages" / filename,
            title=title,
            icon=icon,
            default=index == 0,
        )
        for index, (filename, title, icon) in enumerate(PAGE_SPECS)
    ]
    selected_page = st.navigation(pages, position="sidebar")
    selected_page.run()


if __name__ == "__main__":
    main()
