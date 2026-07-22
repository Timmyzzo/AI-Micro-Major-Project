"""External large-model advice page."""

from __future__ import annotations

import streamlit as st

from app.components.layout import (
    render_page_header,
    render_section_heading,
    render_status_panel,
)
from powerinsight.services.advice_service import (
    AdviceResult,
    build_advice_snapshot,
    generate_advice,
)
from powerinsight.services.runtime import RuntimeContext


def _context() -> RuntimeContext:
    value = st.session_state.get("runtime_context")
    if not isinstance(value, RuntimeContext):
        st.error("系统尚未初始化，请从应用入口启动。")
        st.stop()
    return value


def _export_markdown(result: AdviceResult, model_name: str, evidence: dict[str, object]) -> str:
    """Build a portable, human-readable advice export."""
    return (
        "# PowerInsight 智能用电建议\n\n"
        f"- 使用模型：{model_name}\n"
        f"- 数据覆盖率：{float(evidence['coverage_ratio']):.2%}\n"
        f"- 累计电量：{evidence['total_energy_kwh']} kWh\n"
        f"- 平均负荷：{evidence['average_power_kw']} kW\n"
        f"- 峰值负荷：{evidence['peak_power_kw']} kW\n\n"
        "## 分析与建议\n\n"
        f"{result.text}\n"
    )


context = _context()
model_name = context.settings.openai_model or "尚未配置模型"
render_page_header(
    eyebrow="AI 用电助手",
    title="智能建议",
    description="调用大模型，根据当前用电数据生成充实、具体的详细建议。",
    badge=model_name,
)

try:
    snapshot = build_advice_snapshot(context)
except ValueError:
    render_status_panel(
        tone="blocked",
        label="数据状态",
        title="用电数据尚未准备",
        description="请先在数据中心准备分析数据。",
    )
    st.stop()

evidence = snapshot.evidence
metrics = st.columns(4)
metrics[0].metric("有效数据覆盖率", f"{float(evidence['coverage_ratio']):.2%}")
metrics[1].metric("累计电量", f"{evidence['total_energy_kwh']} kWh")
metrics[2].metric("平均负荷", f"{evidence['average_power_kw']} kW")
metrics[3].metric("峰值负荷", f"{evidence['peak_power_kw']} kW")

st.write("")
render_section_heading(title="生成建议")
st.caption(f"当前模型：{model_name}")

if st.button(
    "生成智能建议",
    type="primary",
    icon=":material/auto_awesome:",
    width="stretch",
    key="generate_advice",
):
    with st.spinner("大模型正在分析当前用电数据……"):
        st.session_state["advice_result"] = generate_advice(snapshot, context.settings)

stored = st.session_state.get("advice_result")
result = stored if isinstance(stored, AdviceResult) else None
if result is not None and result.mode == "api":
    st.success("智能建议已生成。")
    st.markdown(result.text)
    st.download_button(
        "一键导出建议（Markdown）",
        data=_export_markdown(result, model_name, evidence).encode("utf-8"),
        file_name="powerinsight_advice.md",
        mime="text/markdown",
        icon=":material/download:",
        width="stretch",
    )
elif result is not None and result.diagnostic == "not_configured":
    st.error("大模型连接信息尚未完整配置。")
elif result is not None:
    st.error(f"大模型调用失败：{result.diagnostic or '未知错误'}")
