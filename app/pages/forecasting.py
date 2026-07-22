"""Presentation-first 24-hour load forecasting page."""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app.components.layout import render_page_header, render_section_heading, render_status_panel
from app.theme import style_plotly_figure
from powerinsight.forecasting.registry import RegisteredModel
from powerinsight.services.forecast_service import (
    ForecastError,
    ForecastResult,
    ForecastService,
    presentation_model_name,
)
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
    suffix = " · 推荐" if model.is_default else ""
    return f"{presentation_model_name(model)}{suffix}"


def _render_model_card(model: RegisteredModel) -> None:
    render_section_heading(
        title="当前模型",
    )
    facts = st.columns(3)
    facts[0].metric("模型", presentation_model_name(model))
    facts[1].metric("MAE 平均绝对误差", f"{model.test_mae:.4f} kW")
    facts[2].metric("RMSE 均方根误差", f"{model.test_rmse:.4f} kW")


def _training_history_frame(
    service: ForecastService,
    models: tuple[RegisteredModel, ...],
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for model in models:
        history = service.load_metrics(model).get("training_history")
        if not isinstance(history, list):
            continue
        for item in history:
            if not isinstance(item, dict):
                continue
            rows.append(
                {
                    "模型": presentation_model_name(model),
                    "训练轮次 Epoch": item.get("epoch"),
                    "训练损失 Train Loss": item.get("train_loss"),
                    "验证集 MAE 平均绝对误差（kW）": item.get("validation_mae"),
                }
            )
    return pd.DataFrame(rows)


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
        title="预测指标",
    )
    primary = st.columns(3)
    primary[0].metric("MAE 平均绝对误差", f"{float(test['mae']):.4f} kW")
    primary[1].metric("RMSE 均方根误差", f"{float(test['rmse']):.4f} kW")
    primary[2].metric("R² 决定系数", f"{float(test['r2']):.4f}")
    percentage = st.columns(2)
    percentage[0].metric("WAPE 加权绝对百分比误差", f"{float(test['wape']):.2%}")
    percentage[1].metric(
        "sMAPE 对称平均绝对百分比误差",
        f"{float(test['smape']):.2%}",
    )
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
                        "MAE 平均绝对误差（kW）": value.get("mae"),
                        "RMSE 均方根误差（kW）": value.get("rmse"),
                        "WAPE 加权绝对百分比误差": value.get("wape"),
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
                    name="MAE 平均绝对误差",
                    line={"color": ACCENT, "width": 2},
                ),
                go.Scatter(
                    x=step_frame["minutes"] / 60.0,
                    y=step_frame["rmse"],
                    mode="lines",
                    name="RMSE 均方根误差",
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
    eyebrow="智能预测",
    title="负荷预测",
    description="选择时间和模型，预测未来 24 小时负荷。",
    badge="24 小时预测",
)

if availability.status == "blocked":
    render_status_panel(
        tone="blocked",
        label="预测依赖",
        title=availability.title,
        description=availability.reason,
        next_step=availability.next_step,
    )
    st.stop()

render_section_heading(
    title="开始预测",
)
control_columns = st.columns((1.2, 1.2, 0.7), gap="large", vertical_alignment="bottom")
selected_start = control_columns[0].selectbox(
    "预测时间",
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
run_forecast = control_columns[2].button(
    "开始预测",
    type="primary",
    icon=":material/online_prediction:",
    key="forecast_run",
    width="stretch",
)

assert isinstance(selected_start, datetime)
assert isinstance(selected_model, RegisteredModel)
_render_model_card(selected_model)

st.write("")
render_section_heading(
    title="模型对比",
)
st.dataframe(service.comparison_frame(availability.models), hide_index=True, width="stretch")
training_history = _training_history_frame(service, availability.models)
if not training_history.empty:
    with st.expander("查看模型训练过程"):
        st.dataframe(training_history, hide_index=True, width="stretch")

if run_forecast:
    try:
        with st.spinner("正在生成负荷预测……"):
            result = service.predict(
                model_id=selected_model.model_id,
                forecast_start=selected_start,
                requested_device="auto",
                allow_cache=True,
            )
        st.session_state["forecast_result"] = result
    except ForecastError as exc:
        st.session_state.pop("forecast_result", None)
        render_status_panel(
            tone="failed",
            label="预测状态",
            title=exc.title,
            description=exc.reason,
            next_step=exc.next_step,
        )

stored_result = st.session_state.get("forecast_result")
result = stored_result if isinstance(stored_result, ForecastResult) else None
if (
    result is None
    or result.model.model_id != selected_model.model_id
    or result.forecast_start != selected_start
):
    st.info("选择预测时间和模型后，点击“开始预测”。")
    st.stop()

st.success(f"预测完成 · {presentation_model_name(result.model)} · {result.latency_ms:.1f} ms")

st.write("")
render_section_heading(
    title="预测结果",
    description="灰线为历史负荷，绿线为实际值，蓝线为预测值。",
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
