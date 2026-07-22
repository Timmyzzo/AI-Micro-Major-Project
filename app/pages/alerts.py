"""Historical replay and alert page."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app.components.layout import render_page_header, render_section_heading, render_status_panel
from app.theme import style_plotly_figure
from powerinsight.alerts import Alert
from powerinsight.services.alert_service import AlertEvaluation, AlertService
from powerinsight.services.forecast_service import (
    ForecastError,
    ForecastResult,
    ForecastService,
    presentation_model_name,
)
from powerinsight.services.runtime import RuntimeContext

SEVERITY_LABELS = {"info": "信息", "attention": "关注", "critical": "严重"}
TYPE_LABELS = {"data_quality": "数据质量", "rule": "规则", "residual": "预测残差"}


def _context() -> RuntimeContext:
    value = st.session_state.get("runtime_context")
    if not isinstance(value, RuntimeContext):
        st.error("运行上下文尚未初始化，请从应用入口启动。")
        st.stop()
    return value


def _load_result(service: ForecastService) -> ForecastResult | None:
    availability = service.inspect_availability()
    if availability.status == "blocked":
        render_status_panel(
            tone="blocked",
            label="预警依赖",
            title=availability.title,
            description=availability.reason,
            next_step=availability.next_step,
        )
        return None
    columns = st.columns((1.2, 1.2), gap="large")
    start = columns[0].selectbox(
        "回放时间",
        availability.origins,
        format_func=lambda value: value.strftime("%Y-%m-%d %H:%M"),
    )
    model = columns[1].selectbox(
        "预测模型",
        availability.models,
        format_func=lambda value: (
            presentation_model_name(value) + (" · 推荐" if value.is_default else "")
        ),
    )
    if st.button(
        "一键启动监测",
        type="primary",
        icon=":material/play_arrow:",
        width="stretch",
    ):
        try:
            result = service.predict(
                model_id=model.model_id,
                forecast_start=start,
                requested_device="auto",
                allow_cache=True,
            )
            st.session_state["alert_forecast_result"] = result
            st.session_state["replay_index"] = 0
            st.session_state["replay_running"] = True
            st.rerun()
        except ForecastError as exc:
            render_status_panel(
                tone="failed",
                label="预警状态",
                title=exc.title,
                description=exc.reason,
                next_step=exc.next_step,
            )
    value = st.session_state.get("alert_forecast_result")
    return value if isinstance(value, ForecastResult) else None


def _replay_figure(result: ForecastResult, index: int, alerts: tuple[Alert, ...]) -> go.Figure:
    visible = result.forecast.iloc[: index + 1]
    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=visible["timestamp"],
            y=visible["y_true_kw"],
            name="真实负荷",
            mode="lines+markers",
            line={"color": "#2f9e5b", "width": 2},
        )
    )
    figure.add_trace(
        go.Scatter(
            x=visible["timestamp"],
            y=visible["y_pred_kw"],
            name="预测负荷",
            mode="lines",
            line={"color": "#0a84ff", "width": 2},
        )
    )
    current_end = pd.Timestamp(visible["timestamp"].iat[-1])
    event_times = [
        item.start_time
        for item in alerts
        if item.alert_type != "data_quality"
        and item.start_time is not None
        and pd.Timestamp(item.start_time) <= current_end
    ]
    if event_times:
        event_frame = visible.loc[visible["timestamp"].isin(event_times)]
        figure.add_trace(
            go.Scatter(
                x=event_frame["timestamp"],
                y=event_frame["y_true_kw"],
                name="已触发预警",
                mode="markers",
                marker={"color": "#d93025", "size": 9, "symbol": "diamond"},
            )
        )
    style_plotly_figure(
        figure,
        title="历史回测片段逐步回放",
        xaxis_title="数据集本地时间",
        yaxis_title="总有功功率（kW）",
        height=430,
    )
    figure.update_layout(hovermode="x unified")
    return figure


def _visible_alerts(evaluation: AlertEvaluation, current_time: pd.Timestamp) -> tuple[Alert, ...]:
    return tuple(
        alert
        for alert in evaluation.alerts
        if alert.alert_type == "data_quality"
        or alert.start_time is None
        or pd.Timestamp(alert.start_time) <= current_time
    )


@st.fragment(run_every=0.5)
def _render_monitoring(result: ForecastResult, evaluation: AlertEvaluation) -> None:
    point_count = len(result.forecast)
    index = int(st.session_state.get("replay_index", 0))
    index = min(max(index, 0), point_count - 1)
    running = bool(st.session_state.get("replay_running", False))

    if running:
        st.info("正在播放监测过程，每 0.5 秒更新一个预测点。")
    else:
        st.success("监测播放已完成，可拖动滑块回看任意时间点。")
        index = st.slider("回看监测时间点", 0, point_count - 1, index)
        st.session_state["replay_index"] = index

    st.progress((index + 1) / point_count, text=f"播放进度：{index + 1} / {point_count}")
    current_time = pd.Timestamp(result.forecast["timestamp"].iat[index])
    visible_alerts = _visible_alerts(evaluation, current_time)
    st.plotly_chart(
        _replay_figure(result, index, evaluation.alerts),
        width="stretch",
        theme="streamlit",
    )

    metrics = st.columns(4)
    metrics[0].metric("当前时间", current_time.strftime("%m-%d %H:%M"))
    metrics[1].metric("已回放点", f"{index + 1} / {point_count}")
    metrics[2].metric("当前真实负荷", f"{result.forecast['y_true_kw'].iat[index]:.3f} kW")
    metrics[3].metric("已出现预警", len(visible_alerts))

    render_section_heading(title="预警记录")
    types = st.multiselect(
        "预警类型",
        options=tuple(TYPE_LABELS),
        default=tuple(TYPE_LABELS),
        format_func=TYPE_LABELS.__getitem__,
    )
    severities = st.multiselect(
        "等级",
        options=tuple(SEVERITY_LABELS),
        default=tuple(SEVERITY_LABELS),
        format_func=SEVERITY_LABELS.__getitem__,
    )
    filtered = tuple(
        item for item in visible_alerts if item.alert_type in types and item.severity in severities
    )
    display = evaluation.export_frame()
    if filtered:
        display = display.loc[display["alert_id"].isin({item.alert_id for item in filtered})].copy()
        display["alert_type"] = display["alert_type"].map(TYPE_LABELS)
        display["severity"] = display["severity"].map(SEVERITY_LABELS)
        display = display[
            [
                "severity",
                "alert_type",
                "start_time",
                "title",
                "observed_value",
                "threshold",
                "score",
            ]
        ].rename(
            columns={
                "severity": "等级",
                "alert_type": "类型",
                "start_time": "时间",
                "title": "预警内容",
                "observed_value": "观测值",
                "threshold": "阈值",
                "score": "评分",
            }
        )
        st.dataframe(display, hide_index=True, width="stretch")
    else:
        st.info("当前回放位置和筛选条件下没有预警。")
    st.download_button(
        "导出全部预警 CSV",
        data=evaluation.export_frame().to_csv(index=False).encode("utf-8-sig"),
        file_name=f"alerts_{result.forecast_id}.csv",
        mime="text/csv",
        width="stretch",
    )

    if running:
        if index < point_count - 1:
            st.session_state["replay_index"] = index + 1
        else:
            st.session_state["replay_running"] = False
            st.rerun()


context = _context()
render_page_header(
    eyebrow="异常监测",
    title="监测预警",
    description="一键扫描整段历史负荷，查看异常时间、等级和变化趋势。",
    badge="历史回放",
)

render_section_heading(
    title="选择监测范围",
)
forecast_result = _load_result(ForecastService(context))
if forecast_result is None:
    st.stop()

evaluation = AlertService(context).evaluate(forecast_result)
_render_monitoring(forecast_result, evaluation)
