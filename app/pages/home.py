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
from powerinsight.services.forecast_service import ForecastService
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
forecast_availability = ForecastService(context).inspect_availability()
forecast_ready = forecast_availability.status == "ready"

render_page_header(
    eyebrow="PowerInsight · 系统总览",
    title="当前状态，一目了然",
    description="聚焦已验证的数据、分析、预测和预警；剩余范围已收缩为一个可选 API 建议入口。",
    badge="M4 已验证" if forecast_ready else "M3 已验证",
)

if data_ready and data_state.manifest is not None:
    split_counts = data_state.manifest.splits["counts"]
    render_status_panel(
        tone="ready",
        label="核心状态",
        title="M2 数据与 M3 分析基础可用",
        description=(
            "内置 CSV 已建立稳定身份，质量报告、15 分钟聚合、固定月份切分与 manifest 均可读取。"
        ),
        evidence=(
            data_state.manifest.dataset_id,
            data_state.manifest.preprocess_id,
            f"15 分钟点数 {sum(split_counts.values()):,}",
        ),
        next_step="前往用电分析查看真实历史 KPI、趋势、周期和分项结构。",
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
        description="预测和预警使用确定性结果；大模型只在用户点击后生成简短文字建议。",
    )
    if forecast_ready:
        default_model = next(
            (model for model in forecast_availability.models if model.is_default),
            forecast_availability.models[0],
        )
        render_status_panel(
            tone="success",
            label="模型状态",
            title="M4 真实模型闭环可用",
            description="已完成同窗口基线对比、验证集选模、固定测试评估和分步 90% 共形区间。",
            evidence=(
                status.model_status,
                f"默认 {default_model.display_name}",
                f"测试 MAE {default_model.test_mae:.4f} kW",
            ),
            next_step="前往负荷预测选择固定测试起点，运行即时推理或加载离线缓存。",
        )
    else:
        render_status_panel(
            tone="planned",
            label="模型状态",
            title="尚未训练任何模型",
            description="当前没有兼容模型、预测区间或测试指标，页面加载也不会触发训练。",
            evidence=(status.model_status, "无预测结果", "无模型指标"),
            next_step="按固定时间切分进入 M4 模型训练与评估；M3 页面不会生成预测。",
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
        ("已完成 · M3", "确定性 KPI、历史趋势、周期规律、分项结构与本地证据摘要"),
        (
            "已完成 · M4" if forecast_ready else "后续 · M4",
            "模型对比、验证集选模、测试评估、共形区间、缓存和只加载推理页面"
            if forecast_ready
            else "训练与评估模型，并接入只加载推理页面",
        ),
        ("已完成 · M5 核心", "历史回放、三类确定性预警和 CSV 导出"),
        ("精简收尾", "一个可选的大模型 API 简短建议入口；不建设优化平台或完整报告系统"),
    )
)

st.write("")
render_status_panel(
    tone="information",
    label="用户控制",
    title="耗时操作只由明确动作触发",
    description=(
        "完整校验和预处理只在数据中心由按钮启动；预测只由负荷预测页按钮触发；"
        "页面刷新不会训练模型或调用外部 API；API 只由智能建议页按钮触发。"
    ),
)
