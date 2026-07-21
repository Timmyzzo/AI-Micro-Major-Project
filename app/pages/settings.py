"""Non-sensitive runtime diagnostics page."""

from __future__ import annotations

import streamlit as st

from powerinsight.services.runtime import RuntimeContext


def _get_context() -> RuntimeContext:
    context = st.session_state.get("runtime_context")
    if not isinstance(context, RuntimeContext):
        st.error("运行上下文尚未初始化，请从应用入口启动。")
        st.stop()
    return context


context = _get_context()
status = context.status

st.title("系统设置与诊断")
st.caption("只显示非敏感环境信息；API Key 不会回显、写入 YAML、SQLite 或日志。")

diagnostics = [
    {"项目": "Python", "状态": status.python_version},
    {"项目": "PyTorch", "状态": status.torch_version},
    {"项目": "CUDA", "状态": "可用" if status.cuda_available else "不可用，使用 CPU 降级"},
    {"项目": "CUDA Runtime", "状态": status.cuda_runtime or "无"},
    {"项目": "GPU", "状态": status.gpu_name or "未检测到"},
    {"项目": "配置来源", "状态": " → ".join(status.config_sources)},
    {"项目": "原始数据", "状态": status.data_status},
    {"项目": "数据库", "状态": status.database_status},
    {"项目": "LLM", "状态": status.llm_status},
]
st.table(diagnostics)

st.subheader("当前安全边界")
st.markdown(
    "- 页面加载不调用大模型。\n"
    "- 页面加载不启动训练。\n"
    "- 当前数据库只保存空元数据表，不保存 26 万行原始时序。\n"
    "- 未配置 API Key 时应用仍可正常启动。"
)
