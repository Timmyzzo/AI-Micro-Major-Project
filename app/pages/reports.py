"""Minimal local summary with one optional large-model advice call."""

from __future__ import annotations

import streamlit as st

from app.components.layout import render_page_header, render_section_heading, render_status_panel
from powerinsight.services.advice_service import (
    AdviceResult,
    build_advice_snapshot,
    generate_advice,
)
from powerinsight.services.runtime import RuntimeContext


def _context() -> RuntimeContext:
    value = st.session_state.get("runtime_context")
    if not isinstance(value, RuntimeContext):
        st.error("运行上下文尚未初始化，请从应用入口启动。")
        st.stop()
    return value


context = _context()
render_page_header(
    eyebrow="精简功能 · API 建议",
    title="智能建议",
    description="用本地聚合结果生成简短建议；配置后可主动调用一次大模型 API。",
    badge="可选 API",
)

try:
    snapshot = build_advice_snapshot(context)
except ValueError:
    render_status_panel(
        tone="blocked",
        label="数据依赖",
        title="尚无可用分析摘要",
        description="智能建议只读取已经验证的内置数据分析结果。",
        next_step="先在数据中心完成内置数据处理。",
    )
    st.stop()

evidence = snapshot.evidence
metrics = st.columns(4)
metrics[0].metric("覆盖率", f"{float(evidence['coverage_ratio']):.2%}")
metrics[1].metric("累计电量", f"{evidence['total_energy_kwh']} kWh")
metrics[2].metric("平均负荷", f"{evidence['average_power_kw']} kW")
metrics[3].metric("峰值负荷", f"{evidence['peak_power_kw']} kW")

render_section_heading(
    title="简短建议",
    description="默认使用本地模板；只有点击按钮时才发送聚合摘要，不发送原始 CSV 或完整时序。",
)
stored = st.session_state.get("advice_result")
result = stored if isinstance(stored, AdviceResult) else AdviceResult(snapshot.template, "template")

if context.settings.llm_configured:
    if st.button("调用大模型生成简短建议", type="primary", width="stretch"):
        result = generate_advice(snapshot, context.settings)
        st.session_state["advice_result"] = result
else:
    st.info(
        "未配置大模型 API，当前显示本地模板。需要时设置 "
        "LLM_ENABLED、OPENAI_API_KEY 和 OPENAI_MODEL。"
    )

st.markdown(result.text)
if result.mode == "api":
    st.success("本次建议由已配置的大模型 API 生成。")
elif result.diagnostic and result.diagnostic != "not_configured":
    st.warning(f"API 调用失败，已回退本地模板（{result.diagnostic}）。")

with st.expander("查看发送给 API 的聚合摘要", expanded=False):
    st.json(evidence)

st.caption("大模型不会参与数据处理、模型预测、预警分级或数值计算。")
