"""M5 historical replay and deterministic alert page."""

from __future__ import annotations

from typing import Literal, cast

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app.components.layout import render_page_header, render_section_heading, render_status_panel
from app.theme import style_plotly_figure
from powerinsight.alerts import Alert
from powerinsight.services.alert_service import AlertEvaluation, AlertService
from powerinsight.services.forecast_service import ForecastError, ForecastResult, ForecastService
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
            evidence=availability.evidence,
            next_step=availability.next_step,
        )
        return None
    columns = st.columns((1.3, 1.4, 0.8), gap="large")
    start = columns[0].selectbox(
        "回放起点",
        availability.origins,
        format_func=lambda value: value.strftime("%Y-%m-%d %H:%M"),
    )
    model = columns[1].selectbox(
        "冻结模型",
        availability.models,
        format_func=lambda value: value.display_name + (" · 默认" if value.is_default else ""),
    )
    requested_device = cast(
        Literal["auto", "cpu", "cuda"],
        columns[2].selectbox("推理设备", ("auto", "cpu", "cuda")),
    )
    if st.button("载入回放与预警", type="primary", width="stretch"):
        try:
            st.session_state["alert_forecast_result"] = service.predict(
                model_id=model.model_id,
                forecast_start=start,
                requested_device=requested_device,
                allow_cache=True,
            )
            st.session_state["replay_index"] = 0
        except ForecastError as exc:
            render_status_panel(
                tone="failed",
                label=exc.code,
                title=exc.title,
                description=exc.reason,
                evidence=exc.evidence,
                next_step=exc.next_step,
            )
    value = st.session_state.get("alert_forecast_result")
    return value if isinstance(value, ForecastResult) else None


def _replay_controls(point_count: int) -> int:
    index = int(st.session_state.get("replay_index", 0))
    index = min(max(index, 0), point_count - 1)
    columns = st.columns((0.8, 0.8, 0.8, 0.8, 1.4), gap="small")
    if columns[0].button("继续", width="stretch"):
        index = min(index + int(st.session_state.get("replay_step", 4)), point_count - 1)
    if columns[1].button("暂停", width="stretch"):
        st.session_state["replay_paused"] = True
    if columns[2].button("单步", width="stretch"):
        index = min(index + 1, point_count - 1)
    if columns[3].button("重置", width="stretch"):
        index = 0
    step = columns[4].select_slider("每次继续推进", options=(1, 2, 4, 8, 16), value=4)
    st.session_state["replay_step"] = step
    index = st.slider("回放位置", 0, point_count - 1, index, label_visibility="collapsed")
    st.session_state["replay_index"] = index
    return index


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


context = _context()
render_page_header(
    eyebrow="M5 · 智能应用闭环",
    title="监测预警",
    description="只读回放历史真实值，并用质量、稳健阈值和预测区间生成可追踪预警。",
    badge="确定性规则",
)
st.warning("统计异常不等于电气故障；本页仅用于课程演示，不作为安全或运维依据。")

render_section_heading(
    title="回放来源",
    description="使用冻结 M4 回测结果；页面不训练模型、不修改原始数据，也不调用外部 API。",
)
forecast_result = _load_result(ForecastService(context))
if forecast_result is None:
    st.stop()

evaluation = AlertService(context).evaluate(forecast_result)
index = _replay_controls(len(forecast_result.forecast))
current_time = pd.Timestamp(forecast_result.forecast["timestamp"].iat[index])
visible_alerts = _visible_alerts(evaluation, current_time)
st.plotly_chart(
    _replay_figure(forecast_result, index, evaluation.alerts),
    width="stretch",
    theme="streamlit",
)

metrics = st.columns(4)
metrics[0].metric("当前时间", current_time.strftime("%m-%d %H:%M"))
metrics[1].metric("已回放点", f"{index + 1} / {len(forecast_result.forecast)}")
metrics[2].metric("当前真实负荷", f"{forecast_result.forecast['y_true_kw'].iat[index]:.3f} kW")
metrics[3].metric("已出现预警", len(visible_alerts))

render_section_heading(
    title="预警证据",
    description="等级由固定规则计算；相同数据、预测、阈值和规则版本产生相同 alert_id 与等级。",
)
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
    st.dataframe(
        display[
            [
                "severity",
                "alert_type",
                "start_time",
                "title",
                "observed_value",
                "threshold",
                "score",
                "evidence_ids",
            ]
        ],
        hide_index=True,
        width="stretch",
    )
else:
    st.info("当前回放位置和筛选条件下没有预警。")

thresholds = evaluation.thresholds
st.caption(
    "训练段稳健阈值 · "
    f"负荷关注 {thresholds.load_attention_kw:.3f} kW / 严重 {thresholds.load_critical_kw:.3f} kW；"
    f"变化关注 {thresholds.change_attention_kw:.3f} kW / "
    f"严重 {thresholds.change_critical_kw:.3f} kW；"
    f"来源：{thresholds.source}。"
)
st.download_button(
    "导出全部预警 CSV",
    data=evaluation.export_frame().to_csv(index=False).encode("utf-8-sig"),
    file_name=f"alerts_{forecast_result.forecast_id}.csv",
    mime="text/csv",
    width="stretch",
)
