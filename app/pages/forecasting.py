"""Load-only M4 business page for auditable 24-hour forecasts."""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app.components.layout import render_page_header, render_section_heading, render_status_panel
from app.theme import style_plotly_figure
from powerinsight.forecasting.registry import RegisteredModel
from powerinsight.services.forecast_service import ForecastError, ForecastResult, ForecastService
from powerinsight.services.runtime import RuntimeContext

ACCENT = "#0a84ff"
HISTORY = "#6e7781"
TRUTH = "#2f9e5b"
INTERVAL = "rgba(10, 132, 255, 0.18)"
OUTSIDE = "#d93025"


def _get_context() -> RuntimeContext:
    context = st.session_state.get("runtime_context")
    if not isinstance(context, RuntimeContext):
        st.error("运行上下文尚未初始化，请从应用入口启动。")
        st.stop()
    return context


def _model_label(model: RegisteredModel) -> str:
    suffix = " · 默认" if model.is_default else ""
    return f"{model.display_name}{suffix}"


def _render_model_card(model: RegisteredModel) -> None:
    render_section_heading(
        title="模型卡",
        description="模型、缩放器、指标和区间均绑定到同一数据身份与配置指纹。",
    )
    facts = st.columns(4)
    facts[0].metric("模型", model.display_name)
    facts[1].metric("测试 MAE", f"{model.test_mae:.4f} kW")
    facts[2].metric("测试 RMSE", f"{model.test_rmse:.4f} kW")
    facts[3].metric("默认模型", "是" if model.is_default else "否")
    st.caption(
        f"run_id：{model.run_id} · dataset_id：{model.dataset_id} · "
        f"preprocess_id：{model.preprocess_id}"
    )
    with st.expander("查看完整模型卡与限制", expanded=False):
        st.write(f"配置指纹：`{model.config_fingerprint}`")
        st.write(f"代码提交：`{model.code_commit}`")
        st.write(
            f"固定切分：1—4 月训练、5 月验证、6 月测试；"
            f"{model.context_length} 点历史预测 {model.prediction_length} 点未来。"
        )
        st.write(
            f"训练设备：{model.device}；训练耗时：{model.training_seconds:.3f} 秒；"
            f"峰值模型显存：{_memory_text(model.peak_gpu_memory_bytes)}。"
        )
        st.write(model.default_reason)
        for limitation in model.known_limitations:
            st.write(f"- {limitation}")


def _memory_text(value: int | None) -> str:
    return "不适用" if value is None else f"{value / (1024**2):.1f} MiB"


def _forecast_figure(result: ForecastResult) -> go.Figure:
    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=result.context["timestamp"],
            y=result.context["global_active_power_kw"],
            mode="lines",
            name="历史上下文",
            line={"color": HISTORY, "width": 1.3},
            hovertemplate="%{x|%Y-%m-%d %H:%M}<br>%{y:.3f} kW<extra></extra>",
        )
    )
    forecast = result.forecast
    figure.add_trace(
        go.Scatter(
            x=forecast["timestamp"],
            y=forecast["upper_kw"],
            mode="lines",
            line={"width": 0},
            hoverinfo="skip",
            showlegend=False,
        )
    )
    figure.add_trace(
        go.Scatter(
            x=forecast["timestamp"],
            y=forecast["lower_kw"],
            mode="lines",
            name="90% 共形区间",
            line={"width": 0},
            fill="tonexty",
            fillcolor=INTERVAL,
            hovertemplate="下界 %{y:.3f} kW<extra></extra>",
        )
    )
    figure.add_trace(
        go.Scatter(
            x=forecast["timestamp"],
            y=forecast["y_true_kw"],
            mode="lines",
            name="回测真实值",
            line={"color": TRUTH, "width": 1.8},
            hovertemplate="%{x|%Y-%m-%d %H:%M}<br>真实 %{y:.3f} kW<extra></extra>",
        )
    )
    figure.add_trace(
        go.Scatter(
            x=forecast["timestamp"],
            y=forecast["y_pred_kw"],
            mode="lines",
            name="预测值",
            line={"color": ACCENT, "width": 2.2},
            hovertemplate="%{x|%Y-%m-%d %H:%M}<br>预测 %{y:.3f} kW<extra></extra>",
        )
    )
    outside = forecast.loc[forecast["is_outside_interval"]]
    if not outside.empty:
        figure.add_trace(
            go.Scatter(
                x=outside["timestamp"],
                y=outside["y_true_kw"],
                mode="markers",
                name="区间外观测",
                marker={"color": OUTSIDE, "size": 7, "symbol": "x"},
                hovertemplate="%{x|%Y-%m-%d %H:%M}<br>区间外 %{y:.3f} kW<extra></extra>",
            )
        )
    figure.add_vline(x=result.forecast_start, line_dash="dot", line_color=HISTORY)
    style_plotly_figure(
        figure,
        title="7 天历史上下文与 24 小时回测预测",
        xaxis_title="数据集本地时间",
        yaxis_title="总有功功率（kW）",
        height=480,
    )
    figure.update_layout(hovermode="x unified")
    return figure


def _render_metrics(result: ForecastResult) -> None:
    test = result.metrics.get("test")
    interval = result.metrics.get("interval")
    if not isinstance(test, dict) or not isinstance(interval, dict):
        return
    render_section_heading(
        title="固定测试集指标",
        description="所有模型使用相同测试起点；测试集没有参与选参、早停或共形校准。",
    )
    columns = st.columns(5)
    columns[0].metric("MAE", f"{float(test['mae']):.4f} kW")
    columns[1].metric("RMSE", f"{float(test['rmse']):.4f} kW")
    columns[2].metric("WAPE", f"{float(test['wape']):.2%}")
    columns[3].metric("sMAPE", f"{float(test['smape']):.2%}")
    columns[4].metric("R²", f"{float(test['r2']):.4f}")
    interval_columns = st.columns(2)
    interval_columns[0].metric("90% 区间覆盖率", f"{float(interval['coverage']):.2%}")
    interval_columns[1].metric("平均区间宽度", f"{float(interval['average_width_kw']):.4f} kW")

    horizons = result.metrics.get("horizons")
    if isinstance(horizons, dict):
        rows = []
        for label in ("1h", "6h", "12h", "24h"):
            value = horizons.get(label)
            if isinstance(value, dict):
                rows.append(
                    {
                        "累计预测范围": label,
                        "MAE（kW）": value.get("mae"),
                        "RMSE（kW）": value.get("rmse"),
                        "WAPE": value.get("wape"),
                    }
                )
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

    steps = result.metrics.get("steps")
    if isinstance(steps, list):
        step_frame = pd.DataFrame(steps)
        figure = go.Figure(
            [
                go.Scatter(
                    x=step_frame["minutes"] / 60.0,
                    y=step_frame["mae"],
                    mode="lines",
                    name="分步 MAE",
                    line={"color": ACCENT, "width": 2},
                ),
                go.Scatter(
                    x=step_frame["minutes"] / 60.0,
                    y=step_frame["rmse"],
                    mode="lines",
                    name="分步 RMSE",
                    line={"color": HISTORY, "width": 1.8},
                ),
            ]
        )
        style_plotly_figure(
            figure,
            title="按预测步长误差",
            xaxis_title="预测步长（小时）",
            yaxis_title="误差（kW）",
        )
        st.plotly_chart(figure, width="stretch", theme="streamlit")


context = _get_context()
service = ForecastService(context)
availability = service.inspect_availability()

render_page_header(
    eyebrow="M4 · 模型闭环",
    title="负荷预测",
    description="加载冻结模型，在固定测试起点回测未来 24 小时，并展示真实指标与 90% 区间。",
    badge="页面不训练",
)

if availability.status == "blocked":
    render_status_panel(
        tone="blocked",
        label="预测依赖",
        title=availability.title,
        description=availability.reason,
        evidence=availability.evidence,
        next_step=availability.next_step,
    )
    st.stop()

render_status_panel(
    tone="ready",
    label="预测依赖",
    title=availability.title,
    description=availability.reason,
    evidence=availability.evidence,
    next_step=availability.next_step,
)

st.write("")
render_section_heading(
    title="预测控制",
    description="起点来自冻结的 2007 年 6 月日级非重叠回测集合；缓存不会绕过模型兼容性检查。",
)
control_columns = st.columns((1.35, 1.4, 0.8, 0.8), gap="large")
selected_start = control_columns[0].selectbox(
    "预测起点",
    options=availability.origins,
    format_func=lambda value: value.strftime("%Y-%m-%d %H:%M"),
    key="forecast_start",
)
selected_model = control_columns[1].selectbox(
    "模型",
    options=availability.models,
    format_func=_model_label,
    key="forecast_model",
)
device_label = control_columns[2].selectbox(
    "设备",
    options=("自动", "CUDA", "CPU"),
    key="forecast_device",
)
control_columns[3].selectbox(
    "预测区间",
    options=("90%",),
    disabled=True,
    key="forecast_interval",
)
allow_cache = st.checkbox(
    "允许复用身份完全一致的离线预测缓存",
    value=True,
    key="forecast_allow_cache",
)
run_forecast = st.button(
    "运行预测",
    type="primary",
    icon=":material/online_prediction:",
    key="forecast_run",
)

assert isinstance(selected_start, datetime)
assert isinstance(selected_model, RegisteredModel)
_render_model_card(selected_model)

st.write("")
render_section_heading(
    title="模型对比",
    description="比较表来自冻结的同起点测试评估；默认模型选择不会触发重新训练。",
)
st.dataframe(service.comparison_frame(availability.models), hide_index=True, width="stretch")

if run_forecast:
    requested_device = {"自动": "auto", "CUDA": "cuda", "CPU": "cpu"}[device_label]
    try:
        with st.spinner("正在校验模型产物并执行推理……"):
            result = service.predict(
                model_id=selected_model.model_id,
                forecast_start=selected_start,
                requested_device=requested_device,  # type: ignore[arg-type]
                allow_cache=allow_cache,
            )
        st.session_state["forecast_result"] = result
    except ForecastError as exc:
        st.session_state.pop("forecast_result", None)
        render_status_panel(
            tone="failed",
            label="预测状态",
            title=exc.title,
            description=exc.reason,
            evidence=(exc.code, *exc.evidence),
            next_step=exc.next_step,
        )

stored_result = st.session_state.get("forecast_result")
result = stored_result if isinstance(stored_result, ForecastResult) else None
if (
    result is None
    or result.model.model_id != selected_model.model_id
    or result.forecast_start != selected_start
):
    render_status_panel(
        tone="information",
        label="预测状态",
        title="等待运行即时预测或加载缓存",
        description="选择控件不会自动推理；只有明确点击后才读取权重和生成结果。",
        evidence=(selected_model.model_id, selected_start.isoformat()),
        next_step="点击“运行预测”。",
    )
    st.stop()

render_status_panel(
    tone="information" if result.status == "cached" else "success",
    label="预测状态",
    title="已加载离线缓存" if result.status == "cached" else "即时预测完成",
    description="结果身份、模型、缩放器、区间与当前数据契约一致。",
    evidence=(
        result.forecast_id,
        f"设备 {result.device}",
        f"推理耗时 {result.latency_ms:.2f} ms",
        result.cache_path_alias,
    ),
    next_step="结合真实值、区间外点和固定测试指标解释结果，不把回测当作未知未来。",
)

st.write("")
render_section_heading(
    title="回测预测与区间",
    description="灰线为 7 天历史，深色线为真实未来，蓝线为预测；红点为 90% 区间外观测。",
)
st.plotly_chart(_forecast_figure(result), width="stretch", theme="streamlit")
_render_metrics(result)

csv_data = result.export_frame().to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
st.download_button(
    "下载预测 CSV",
    data=csv_data,
    file_name=f"{result.forecast_id}.csv",
    mime="text/csv",
    icon=":material/download:",
    key="forecast_download",
)
st.caption(
    "导出包含 forecast_id、model_id、run_id、dataset_id、preprocess_id、配置指纹、"
    "区间等级、生成时间、状态与实际设备。"
)
