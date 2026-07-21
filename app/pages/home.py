"""Home page for the current engineering-skeleton milestone."""

from __future__ import annotations

import streamlit as st

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

st.title("⚡ 智电洞察（PowerInsight）")
st.caption("电力数据智能分析与可视化系统 · 当前阶段：M2 数据闭环")
st.warning("尚未训练任何模型；本页只展示真实数据闭环与已验证环境状态。")

data_col, model_col, gpu_col, llm_col, database_col = st.columns(5)
data_col.metric(
    "数据",
    "M2 闭环可用" if data_ready else "原始文件可用" if status.data_file_exists else "原始文件缺失",
)
model_col.metric("模型", "尚未训练")
gpu_col.metric("GPU", "CUDA 可用" if status.cuda_available else "CPU 模式")
llm_col.metric("LLM", "已配置" if status.llm_configured else "未配置/已禁用")
database_col.metric("数据库", "可访问" if status.database_accessible else "不可访问")

st.subheader("状态说明")
st.markdown(
    "\n".join(
        (
            f"- **数据：** {'15 分钟数据与 manifest 已生成' if data_ready else status.data_status}",
            f"- **模型：** {status.model_status}",
            f"- **GPU：** {status.gpu_name or '未检测到 CUDA 设备'}",
            f"- **LLM：** {status.llm_status}",
            f"- **SQLite：** {status.database_status}",
        )
    )
)

st.info("完整校验和预处理只在数据中心由按钮触发；页面加载不会训练模型或调用外部 API。")
