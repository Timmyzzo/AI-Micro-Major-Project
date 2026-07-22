"""Concise runtime settings and capability summary."""

from __future__ import annotations

import streamlit as st

from app.components.layout import render_fact_list, render_page_header, render_section_heading
from powerinsight.services.forecast_service import ForecastService
from powerinsight.services.runtime import RuntimeContext


def _get_context() -> RuntimeContext:
    context = st.session_state.get("runtime_context")
    if not isinstance(context, RuntimeContext):
        st.error("系统尚未初始化，请从应用入口启动。")
        st.stop()
    return context


context = _get_context()
status = context.status
forecast = ForecastService(context).inspect_availability()

render_page_header(
    eyebrow="运行信息",
    title="系统设置",
    description="查看计算环境、数据、预测模型和大模型连接信息。",
    badge="系统信息",
)

render_section_heading(title="计算环境")
render_fact_list(
    (
        ("Python", status.python_version),
        ("PyTorch", status.torch_version),
        ("计算设备", status.gpu_name or "CPU"),
        ("CUDA", "可用" if status.cuda_available else "不可用"),
    )
)

st.write("")
render_section_heading(title="功能状态")
render_fact_list(
    (
        ("用电数据", "已就绪" if status.data_file_exists else "不可用"),
        ("预测模型", f"{len(forecast.models)} 个" if forecast.status == "ready" else "待准备"),
        ("大模型 API", "已配置" if context.settings.llm_configured else "等待配置"),
        ("大模型型号", context.settings.openai_model or "尚未配置"),
    )
)
