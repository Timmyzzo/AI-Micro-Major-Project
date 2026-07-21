"""Shared empty-state rendering for functions outside the current milestone."""

from __future__ import annotations

from collections.abc import Sequence

import streamlit as st

from app.components.layout import (
    StatusTone,
    render_fact_list,
    render_page_header,
    render_section_heading,
    render_status_panel,
)
from powerinsight.services.data_service import DataService
from powerinsight.services.runtime import RuntimeContext


def _m2_foundation() -> tuple[StatusTone, str, str, tuple[str, ...]]:
    context = st.session_state.get("runtime_context")
    if not isinstance(context, RuntimeContext):
        return (
            "unavailable",
            "数据基础状态不可用",
            "当前页面不是从 PowerInsight 应用入口启动，无法确认本机 M2 产物。",
            ("业务能力仍保持未启用",),
        )
    state = DataService(context).inspect_builtin_state()
    if state.manifest is not None and state.processed_exists:
        counts = state.manifest.splits["counts"]
        return (
            "ready",
            "M2 数据基础已经具备",
            "原始数据身份、质量报告、15 分钟聚合、固定月份切分和 manifest 均可追踪。",
            (
                state.manifest.dataset_id,
                state.manifest.preprocess_id,
                f"15 分钟点数 {sum(counts.values()):,}",
            ),
        )
    if state.source_exists:
        return (
            "attention",
            "原始数据可用，处理产物尚未就绪",
            "内置 CSV 身份可确认，但当前没有可读取的 M2 处理产物。",
            tuple(item for item in (state.dataset_id, state.source_path_alias) if item),
        )
    return (
        "blocked",
        "原始数据基础缺失",
        "在进入后续业务前，需要先恢复并校验课程提供的只读 CSV。",
        (state.source_path_alias,),
    )


def render_planned_page(
    *,
    title: str,
    purpose: str,
    requirement_ids: Sequence[str],
    capabilities: Sequence[str],
    dependencies: Sequence[str],
    guardrail: str,
) -> None:
    """Render a factual planned state without fabricated data, metrics, or charts."""
    render_page_header(
        eyebrow="后续业务 · 计划状态",
        title=title,
        description=purpose,
        badge="未启用",
    )

    foundation_tone, foundation_title, foundation_description, foundation_evidence = (
        _m2_foundation()
    )
    render_status_panel(
        tone=foundation_tone,
        label="数据基础",
        title=foundation_title,
        description=foundation_description,
        evidence=foundation_evidence,
        next_step="数据基础就绪后，仍需完成本页专属服务和验收，不能直接视为业务已实现。",
    )
    st.write("")
    render_status_panel(
        tone="planned",
        label="业务状态",
        title="能力边界已定义，功能尚未实现",
        description="页面只说明目标、依赖和启用路径，不展示示例数值或伪造业务结果。",
        evidence=tuple(requirement_ids),
        next_step=dependencies[0],
    )

    st.write("")
    plan_col, dependency_col = st.columns((1.12, 1), gap="large")
    with plan_col:
        render_section_heading(
            title="计划能力",
            description="这些内容属于后续里程碑，当前不会在页面加载时计算。",
        )
        render_fact_list(
            tuple(
                (f"能力 {index:02d}", capability)
                for index, capability in enumerate(capabilities, 1)
            )
        )
    with dependency_col:
        render_section_heading(
            title="启用前置",
            description="每一项都需要真实实现、测试和可追踪产物。",
        )
        render_fact_list(
            tuple(
                (f"条件 {index:02d}", dependency)
                for index, dependency in enumerate(dependencies, 1)
            )
        )

    st.write("")
    render_status_panel(
        tone="disabled",
        label="当前安全边界",
        title="本页保持只读计划状态",
        description=guardrail,
        evidence=("不自动训练", "不调用外部 API", "不生成虚假指标"),
        next_step="进入对应业务里程碑后，用真实服务、数据和测试替换此状态。",
    )
