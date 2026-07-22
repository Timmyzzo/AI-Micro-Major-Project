"""Presentation-first overview for PowerInsight."""

from __future__ import annotations

import streamlit as st

from app.components.layout import (
    ConnectionTone,
    render_connection_status,
    render_page_header,
    render_section_heading,
)
from powerinsight.services import advice_service
from powerinsight.services.advice_service import LlmProbeResult
from powerinsight.services.data_service import DataService
from powerinsight.services.forecast_service import ForecastService
from powerinsight.services.runtime import RuntimeContext


def _get_context() -> RuntimeContext:
    context = st.session_state.get("runtime_context")
    if not isinstance(context, RuntimeContext):
        st.error("系统尚未初始化，请从应用入口启动。")
        st.stop()
    return context


def _connection_view(
    context: RuntimeContext,
    result: LlmProbeResult | None,
) -> tuple[ConnectionTone, str, str]:
    if result is not None and result.status == "success":
        latency = f"{result.latency_ms:.0f} ms" if result.latency_ms is not None else "已响应"
        return "success", "连接正常", latency
    if result is not None and result.status == "failed":
        return "failed", "连接失败", result.diagnostic or "请稍后重试"
    if result is not None and result.status == "unconfigured":
        return "inactive", "等待配置", result.diagnostic or "请补充连接信息"
    if context.settings.llm_configured:
        return "pending", "已配置，等待测试", "点击按钮验证模型响应"
    return "inactive", "等待配置", "补充 API Key 和模型后即可测试"


context = _get_context()
data_state = DataService(context).inspect_builtin_state()
data_ready = data_state.manifest is not None and data_state.processed_exists
forecast = ForecastService(context).inspect_availability()
forecast_ready = forecast.status == "ready"

render_page_header(
    eyebrow="PowerInsight",
    title="系统总览",
    description="查看数据、分析、预测、预警和大模型连接状态。",
    badge="运行中",
)

render_section_heading(title="核心功能")
summary = st.columns(4)
summary[0].metric("数据", "已就绪" if data_ready else "待准备")
summary[1].metric("用电分析", "可用" if data_ready else "待准备")
summary[2].metric(
    "负荷预测",
    f"{len(forecast.models)} 个模型" if forecast_ready else "待准备",
)
summary[3].metric("监测预警", "可用" if forecast_ready else "待准备")

if data_ready and data_state.manifest is not None:
    manifest = data_state.manifest
    coverage = 1.0 - (
        manifest.quality_report.measurement_missing_row_count / manifest.source_rows
        if manifest.source_rows
        else 0.0
    )
    details = st.columns(3)
    details[0].metric("数据时间范围", f"{manifest.start_time:%Y-%m} 至 {manifest.end_time:%Y-%m}")
    details[1].metric("分析粒度", "15 分钟")
    details[2].metric("有效数据覆盖率", f"{coverage:.2%}")

st.write("")
render_section_heading(title="大模型 API")
stored = st.session_state.get("llm_probe_result")
probe = stored if isinstance(stored, LlmProbeResult) else None
tone, connection_status, detail = _connection_view(context, probe)
render_connection_status(
    tone=tone,
    status=connection_status,
    model=context.settings.openai_model or "尚未配置模型",
    detail=detail,
)

if st.button(
    "测试 API 连接",
    type="primary",
    icon=":material/network_check:",
    key="home_llm_probe",
):
    with st.spinner("正在连接大模型……"):
        st.session_state["llm_probe_result"] = advice_service.probe_llm_connection(context.settings)
    st.rerun()

if probe is not None and probe.status == "success":
    st.success(f"模型回复：{probe.text}")
elif probe is not None and probe.status == "failed":
    st.error(f"连接失败：{probe.diagnostic or '未知错误'}")
elif probe is not None and probe.status == "unconfigured":
    st.warning(probe.diagnostic or "请补充大模型连接信息。")

st.write("")
render_section_heading(title="推荐展示顺序")
steps = st.columns(4)
steps[0].metric("1", "查看数据来源")
steps[1].metric("2", "分析用电规律")
steps[2].metric("3", "运行负荷预测")
steps[3].metric("4", "生成智能建议")
