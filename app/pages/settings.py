"""Non-sensitive runtime diagnostics page."""

from __future__ import annotations

import streamlit as st

from app.components.layout import (
    render_fact_list,
    render_page_header,
    render_section_heading,
    render_status_panel,
)
from powerinsight.services.runtime import RuntimeContext


def _get_context() -> RuntimeContext:
    context = st.session_state.get("runtime_context")
    if not isinstance(context, RuntimeContext):
        st.error("运行上下文尚未初始化，请从应用入口启动。")
        st.stop()
    return context


context = _get_context()
status = context.status

render_page_header(
    eyebrow="系统 · 设置与诊断",
    title="环境清楚，边界明确",
    description="按运行环境、配置来源、存储职责和安全边界分组展示非敏感状态。当前页面不提供秘密回显或业务参数写入。",
    badge="只读诊断",
)

render_status_panel(
    tone="ready" if status.database_accessible and status.data_file_exists else "attention",
    label="诊断摘要",
    title="核心运行依赖可检查",
    description=(
        "当前信息来自已验证的运行上下文，不读取或显示 API Key、Authorization 请求头和完整用户路径。"
    ),
    evidence=(
        f"Python {status.python_version}",
        f"PyTorch {status.torch_version}",
        "SQLite 可访问" if status.database_accessible else "SQLite 不可访问",
    ),
    next_step="需要更完整的依赖、CUDA、目录与原始数据检查时，运行 scripts/check_environment.py。",
)

st.write("")
runtime_col, storage_col = st.columns(2, gap="large")
with runtime_col:
    render_section_heading(
        title="运行环境",
        description="计算能力与可降级路径。",
    )
    render_fact_list(
        (
            ("Python", status.python_version),
            ("PyTorch", status.torch_version),
            ("CUDA", "可用" if status.cuda_available else "不可用，使用 CPU 降级"),
            ("CUDA Runtime", status.cuda_runtime or "未提供"),
            ("GPU", status.gpu_name or "未检测到"),
        )
    )

with storage_col:
    render_section_heading(
        title="数据与存储",
        description="时序文件与轻量元数据保持职责分离。",
    )
    render_fact_list(
        (
            ("原始数据", status.data_status),
            ("SQLite", status.database_status),
            ("存储职责", "只存元数据，不存 26 万行原始或聚合时序"),
            ("模型状态", status.model_status),
            ("LLM", status.llm_status),
        )
    )

st.write("")
render_section_heading(
    title="配置来源",
    description="优先级从安全默认值逐层覆盖；秘密不允许写入 YAML。",
)
render_fact_list(
    tuple((f"来源 {index:02d}", source) for index, source in enumerate(status.config_sources, 1))
)

st.write("")
render_status_panel(
    tone="disabled",
    label="安全边界",
    title="秘密不回显，外部调用必须主动触发",
    description=(
        "页面加载不训练模型、不调用大模型；只有智能建议页按钮可以发起一次请求。"
        "未配置 API Key 时应用仍可启动，Key 也不会回显、写入 YAML、SQLite 或日志。"
    ),
    evidence=("无 Key 回显", "无页面自动调用", "SQLite 仅元数据"),
)
