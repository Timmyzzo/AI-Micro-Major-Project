"""Historical electric-use analytics page."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app.components.layout import (
    render_page_header,
    render_section_heading,
    render_status_panel,
)
from app.theme import style_plotly_figure
from powerinsight.analytics import AnalyticsResult
from powerinsight.services.analytics_service import AnalyticsError, AnalyticsService
from powerinsight.services.runtime import RuntimeContext

ACCENT = "#0a84ff"
SECONDARY = "#6e7781"
WARNING = "#c77800"
SUBMETER_COLORS = ("#0a84ff", "#2f9e5b", "#c77800", "#6e7781")


def _get_context() -> RuntimeContext:
    context = st.session_state.get("runtime_context")
    if not isinstance(context, RuntimeContext):
        st.error("运行上下文尚未初始化，请从应用入口启动。")
        st.stop()
    return context


def _selected_date_range(value: object) -> tuple[date, date] | None:
    if isinstance(value, tuple) and len(value) == 2:
        start, end = value
        if isinstance(start, date) and isinstance(end, date):
            return start, end
    return None


def _format_measurement(value: float | None, unit: str, *, decimals: int = 2) -> str:
    return "—" if value is None else f"{value:,.{decimals}f} {unit}"


def _format_time(value: datetime | None) -> str:
    return "未知" if value is None else value.strftime("%Y-%m-%d %H:%M")


def _render_kpis(result: AnalyticsResult) -> None:
    kpis = result.kpis
    summary = result.range_summary
    primary = st.columns(4)
    primary[0].metric(
        "累计有功电量",
        _format_measurement(kpis.total_active_energy_kwh, "kWh", decimals=1),
    )
    primary[1].metric(
        "平均有功功率",
        _format_measurement(kpis.average_active_power_kw, "kW"),
    )
    primary[2].metric(
        "峰值有功功率",
        _format_measurement(kpis.peak_active_power_kw, "kW"),
    )
    primary[3].metric("有效数据覆盖率", f"{summary.coverage_ratio:.1%}")
    st.caption(f"峰值时间：{_format_time(kpis.peak_time)}")
    secondary = st.columns(4)
    secondary[0].metric(
        "最低有效功率",
        _format_measurement(kpis.minimum_active_power_kw, "kW"),
    )
    secondary[1].metric("理论点数", f"{summary.expected_points:,}")
    secondary[2].metric("实际存在点数", f"{summary.actual_points:,}")
    secondary[3].metric("缺失点数", f"{summary.missing_points:,}")
    st.caption(f"最低值时间：{_format_time(kpis.minimum_time)}")


def _trend_figure(result: AnalyticsResult) -> go.Figure:
    figure = go.Figure(
        go.Scatter(
            x=result.trend["timestamp"],
            y=result.trend["global_active_power_kw"],
            mode="lines",
            name="总有功功率",
            line={"color": ACCENT, "width": 1.8},
            connectgaps=False,
            hovertemplate="%{x|%Y-%m-%d %H:%M}<br>%{y:.3f} kW<extra></extra>",
        )
    )
    style_plotly_figure(
        figure,
        title="历史总有功功率趋势",
        xaxis_title="数据集本地时间",
        yaxis_title="平均功率（kW）",
        height=410,
    )
    figure.update_layout(hovermode="x unified")
    return figure


def _hourly_figure(result: AnalyticsResult) -> go.Figure:
    profile = result.hourly_profile
    custom = profile[["valid_samples", "total_samples", "coverage_ratio"]].to_numpy()
    figure = go.Figure(
        go.Bar(
            x=profile["hour"],
            y=profile["average_power_kw"],
            marker_color=ACCENT,
            name="小时平均",
            customdata=custom,
            hovertemplate=(
                "%{x}:00<br>%{y:.3f} kW<br>有效 %{customdata[0]:,.0f}/%{customdata[1]:,.0f}"
                "<br>覆盖率 %{customdata[2]:.1%}<extra></extra>"
            ),
        )
    )
    return style_plotly_figure(
        figure,
        title="小时规律",
        xaxis_title="小时",
        yaxis_title="有效样本平均功率（kW）",
    )


def _weekday_figure(result: AnalyticsResult) -> go.Figure:
    profile = result.weekday_profile
    custom = profile[["valid_samples", "total_samples", "coverage_ratio"]].to_numpy()
    figure = go.Figure(
        go.Bar(
            x=profile["weekday_label"],
            y=profile["average_power_kw"],
            marker_color=SECONDARY,
            name="星期平均",
            customdata=custom,
            hovertemplate=(
                "%{x}<br>%{y:.3f} kW<br>有效 %{customdata[0]:,.0f}/%{customdata[1]:,.0f}"
                "<br>覆盖率 %{customdata[2]:.1%}<extra></extra>"
            ),
        )
    )
    return style_plotly_figure(
        figure,
        title="星期规律",
        xaxis_title=None,
        yaxis_title="有效样本平均功率（kW）",
    )


def _day_type_figure(result: AnalyticsResult) -> go.Figure:
    figure = go.Figure()
    for day_type, color in (("工作日", ACCENT), ("周末", WARNING)):
        profile = result.day_type_profile.loc[result.day_type_profile["day_type"].eq(day_type)]
        if profile.empty:
            continue
        custom = profile[["valid_samples", "total_samples", "coverage_ratio"]].to_numpy()
        figure.add_trace(
            go.Scatter(
                x=profile["hour"],
                y=profile["average_power_kw"],
                mode="lines+markers",
                name=day_type,
                line={"color": color, "width": 2},
                marker={"size": 5},
                customdata=custom,
                hovertemplate=(
                    f"{day_type} %{{x}}:00<br>%{{y:.3f}} kW"
                    "<br>有效 %{customdata[0]:,.0f}/%{customdata[1]:,.0f}"
                    "<br>覆盖率 %{customdata[2]:.1%}<extra></extra>"
                ),
            )
        )
    return style_plotly_figure(
        figure,
        title="工作日与周末日内对比",
        xaxis_title="小时",
        yaxis_title="有效样本平均功率（kW）",
    )


def _render_submeter(result: AnalyticsResult) -> None:
    rows = [
        {
            "分项": component.label,
            "能量（kWh）": component.energy_kwh,
            "占比": component.share_ratio,
        }
        for component in result.submeter.components
    ]
    frame = pd.DataFrame(rows)
    figure = go.Figure(
        go.Bar(
            x=frame["能量（kWh）"],
            y=frame["分项"],
            orientation="h",
            marker_color=SUBMETER_COLORS,
            customdata=frame[["占比"]].to_numpy(),
            hovertemplate="%{y}<br>%{x:.3f} kWh<extra></extra>",
        )
    )
    style_plotly_figure(
        figure,
        title="分项与未分项电量",
        xaxis_title="累计能量（kWh）",
        yaxis_title=None,
    )
    chart_col, table_col = st.columns((1.15, 1), gap="large")
    with chart_col:
        st.plotly_chart(figure, width="stretch", theme="streamlit")
    with table_col:
        display = frame.copy()
        display["能量（kWh）"] = display["能量（kWh）"].map(
            lambda value: "—" if pd.isna(value) else f"{value:,.3f}"
        )
        display["占比"] = display["占比"].map(
            lambda value: "—" if pd.isna(value) else f"{value:.1%}"
        )
        st.dataframe(display, hide_index=True, width="stretch")


context = _get_context()
service = AnalyticsService(context)
availability = service.inspect_availability()

render_page_header(
    eyebrow="用电洞察",
    title="用电分析",
    description="选择日期，查看负荷趋势、周期规律和分项用电。",
    badge="历史分析",
)

if availability.status == "blocked":
    render_status_panel(
        tone="blocked",
        label="数据依赖",
        title=availability.title,
        description=availability.reason,
        next_step=availability.next_step,
    )
    st.stop()

assert availability.start_time is not None
assert availability.end_time is not None
assert availability.manifest is not None
minimum_date = availability.start_time.date()
maximum_date = availability.end_time.date()
default_start = max(minimum_date, maximum_date - timedelta(days=29))

render_section_heading(
    title="分析范围",
    description="选择需要查看的开始和结束日期。",
)
selected_value = st.date_input(
    "分析日期范围",
    value=(default_start, maximum_date),
    min_value=minimum_date,
    max_value=maximum_date,
    format="YYYY-MM-DD",
    key="analytics_date_range",
)
selected_range = _selected_date_range(selected_value)
if selected_range is None:
    render_status_panel(
        tone="empty",
        label="范围状态",
        title="请选择完整的起止日期",
        description="当前日期范围尚未形成两个边界，因此没有执行分析。",
        next_step="选择开始日期和结束日期；两端日期都会包含在分析中。",
    )
    st.stop()
start_date, end_date = selected_range
if start_date > end_date:
    render_status_panel(
        tone="failed",
        label="范围状态",
        title="日期范围无效",
        description="开始日期不能晚于结束日期。",
        evidence=(f"开始 {start_date}", f"结束 {end_date}"),
        next_step="调整日期后页面会自动重新计算。",
    )
    st.stop()

start_time = datetime.combine(start_date, time.min)
end_exclusive = datetime.combine(end_date + timedelta(days=1), time.min)
try:
    with st.spinner("正在读取处理后 Parquet 并计算确定性分析……"):
        result = service.analyze(start=start_time, end_exclusive=end_exclusive)
except AnalyticsError as exc:
    render_status_panel(
        tone="failed",
        label="分析状态",
        title=exc.title,
        description=exc.reason,
        next_step=exc.next_step,
    )
    st.stop()

if result.status == "empty":
    render_status_panel(
        tone="empty",
        label="分析状态",
        title="所选范围没有有效负荷数据",
        description="未知值保持未知，页面不会把空范围或全缺失范围显示成 0。",
        evidence=(
            f"理论点数 {result.range_summary.expected_points:,}",
            f"实际点数 {result.range_summary.actual_points:,}",
            f"有效点数 {result.range_summary.valid_load_points:,}",
        ),
        next_step="选择包含有效 15 分钟负荷数据的日期范围。",
    )
    st.stop()

if result.status == "attention":
    st.warning("所选范围存在缺失区段，趋势图已保留数据断点。")

st.write("")
render_section_heading(
    title="核心指标",
)
_render_kpis(result)

st.write("")
render_section_heading(
    title="历史趋势",
)
st.plotly_chart(_trend_figure(result), width="stretch", theme="streamlit")

st.write("")
render_section_heading(
    title="周期规律",
)
hour_col, weekday_col = st.columns(2, gap="large")
with hour_col:
    st.plotly_chart(_hourly_figure(result), width="stretch", theme="streamlit")
with weekday_col:
    st.plotly_chart(_weekday_figure(result), width="stretch", theme="streamlit")
st.plotly_chart(_day_type_figure(result), width="stretch", theme="streamlit")

st.write("")
render_section_heading(
    title="分项用电结构",
)
_render_submeter(result)
