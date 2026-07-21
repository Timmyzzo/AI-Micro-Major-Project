"""Native-style overview of the current verified PowerInsight state."""

from __future__ import annotations

import streamlit as st

from app.components.layout import (
    render_fact_list,
    render_page_header,
    render_section_heading,
    render_status_panel,
)
from powerinsight.services.data_service import DataService
from powerinsight.services.runtime import RuntimeContext


def _get_context() -> RuntimeContext:
    context = st.session_state.get("runtime_context")
    if not isinstance(context, RuntimeContext):
        st.error("运行上下文尚未初始化，请从应用入口启动。")
        st.stop()
    return context


context = _get_context()
status = context.status
data_state = DataService(context).inspect_builtin_state()
data_ready = data_state.manifest is not None and data_state.processed_exists

render_page_header(
    eyebrow="PowerInsight · 系统总览",
    title="当前状态，一目了然",
    description=(
        "聚焦已经验证的 M2 数据闭环、运行环境和下一步路径，不提前展示尚未产生的分析或模型结果。"
    ),
    badge="M2 已验证",
)

if data_ready and data_state.manifest is not None:
    split_counts = data_state.manifest.splits["counts"]
    render_status_panel(
        tone="ready",
        label="核心状态",
        title="M2 数据闭环可用",
        description=(
            "内置 CSV 已建立稳定身份，质量报告、15 分钟聚合、固定月份切分与 manifest 均可读取。"
        ),
        evidence=(
            data_state.manifest.dataset_id,
            data_state.manifest.preprocess_id,
            f"15 分钟点数 {sum(split_counts.values()):,}",
        ),
        next_step="前往数据中心复核质量证据，或在后续 M3 阶段实现确定性用电分析。",
    )
elif data_state.source_exists:
    render_status_panel(
        tone="attention",
        label="核心状态",
        title="原始数据可用，M2 产物尚未就绪",
        description="页面只完成了低成本文件身份检查，没有自动执行完整校验或预处理。",
        evidence=tuple(
            item for item in (data_state.dataset_id, data_state.source_path_alias) if item
        ),
        next_step="在数据中心主动运行完整质量校验，并按需生成 M2 处理产物。",
    )
else:
    render_status_panel(
        tone="blocked",
        label="核心状态",
        title="内置原始数据缺失",
        description="后续分析与模型能力都依赖课程提供的只读 CSV，当前不能继续建立数据闭环。",
        evidence=(data_state.source_path_alias,),
        next_step="恢复原始 CSV 后重新启动应用；不要用空文件或修改配置绕过校验。",
    )

st.write("")
model_col, environment_col = st.columns((1.05, 1), gap="large")
with model_col:
    render_section_heading(
        title="模型与智能能力",
        description="数据基础已经形成，但模型、预警、优化和报告仍处于明确的计划状态。",
    )
    render_status_panel(
        tone="planned",
        label="模型状态",
        title="尚未训练任何模型",
        description="当前没有 Ridge、LSTM、PatchTST、预测区间或测试指标，页面加载也不会触发训练。",
        evidence=(status.model_status, "无预测结果", "无模型指标"),
        next_step="先完成 M3 分析闭环，再按固定时间切分进入 M4 模型训练与评估。",
    )

with environment_col:
    render_section_heading(
        title="运行环境",
        description="只显示非敏感、可核对的本机诊断。",
    )
    render_fact_list(
        (
            ("计算设备", status.gpu_name or "未检测到 CUDA 设备，使用 CPU 降级"),
            ("CUDA", "可用" if status.cuda_available else "不可用"),
            ("LLM", status.llm_status),
            ("SQLite", status.database_status),
        )
    )

st.write("")
render_section_heading(
    title="可预期的下一步",
    description="每一阶段只在真实实现和验收后改变状态，避免把计划写成结果。",
)
render_fact_list(
    (
        ("已完成 · M2", "数据校验、缺失治理、15 分钟聚合、固定切分、manifest 与元数据登记"),
        ("下一阶段 · M3", "实现确定性 KPI、历史趋势、周期规律和分项结构；当前尚未开始"),
        ("后续 · M4/M5", "训练与评估模型，再接入残差预警、情景模拟和证据报告"),
    )
)

st.write("")
render_status_panel(
    tone="information",
    label="用户控制",
    title="耗时操作只由明确动作触发",
    description=(
        "完整校验和预处理只在数据中心由按钮启动；页面刷新不会训练模型、生成预测或调用外部 API。"
    ),
)
