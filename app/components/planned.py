"""Shared empty-state rendering for functions outside the current milestone."""

from __future__ import annotations

from collections.abc import Sequence

import streamlit as st


def render_planned_page(
    *,
    title: str,
    purpose: str,
    requirement_ids: Sequence[str],
    dependencies: Sequence[str],
) -> None:
    """Render a factual planned state without fabricated data, metrics, or charts."""
    st.title(title)
    st.info("计划状态：本页面导航已建立，业务功能尚未在当前 M1 工程骨架阶段实现。")
    st.write(purpose)
    st.subheader("对应需求")
    st.markdown("\n".join(f"- `{requirement_id}`" for requirement_id in requirement_ids))
    st.subheader("启用条件")
    st.markdown("\n".join(f"- {dependency}" for dependency in dependencies))
    st.warning("当前页面没有运行数据处理、模型训练、预测、预警、优化或大模型调用。")
