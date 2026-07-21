"""Deterministic historical electric-use analytics page."""

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
    st.caption(
        f"峰值时间：{_format_time(kpis.peak_time)}；"
        "所有指标基于有效 15 分钟数据，未知值不显示为 0。"
    )
    secondary = st.columns(4)
    secondary[0].metric(
        "最低有效功率",
        _format_measurement(kpis.minimum_active_power_kw, "kW"),
    )
    secondary[1].metric("理论点数", f"{summary.expected_points:,}")
    secondary[2].metric("实际存在点数", f"{summary.actual_points:,}")
    secondary[3].metric("缺失点数", f"{summary.missing_points:,}")
    st.caption(f"最低值时间：{_format_time(kpis.minimum_time)}；时间为数据集本地朴素时间。")


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
        st.caption(result.submeter.note)


context = _get_context()
service = AnalyticsService(context)
availability = service.inspect_availability()

render_page_header(
    eyebrow="M3 · 确定性历史分析",
    title="用电分析",
    description="从已验证的 15 分钟处理数据计算真实 KPI、周期规律、分项结构与缺失证据。",
    badge="不训练模型",
)

if availability.status == "blocked":
    render_status_panel(
        tone="blocked",
        label="数据依赖",
        title=availability.title,
        description=availability.reason,
        evidence=availability.evidence,
        next_step=availability.next_step,
    )
    st.stop()

assert availability.start_time is not None
assert availability.end_time is not None
assert availability.manifest is not None
minimum_date = availability.start_time.date()
maximum_date = availability.end_time.date()
default_start = max(minimum_date, maximum_date - timedelta(days=29))

render_status_panel(
    tone="ready",
    label="数据依赖",
    title=availability.title,
    description=availability.reason,
    evidence=availability.evidence,
    next_step=availability.next_step,
)

st.write("")
render_section_heading(
    title="分析范围",
    description="起止日期均包含；内部使用结束日次日 00:00 作为半开区间上界。",
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
        evidence=(exc.code, *exc.evidence),
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

tone = "attention" if result.status == "attention" else "success"
status_title = "分析完成，但存在需要保留的质量限制" if result.status == "attention" else "分析完成"
render_status_panel(
    tone=tone,
    label="分析状态",
    title=status_title,
    description="全部数值来自当前 M2 处理产物；功率、电量、缺失和分项口径彼此分离。",
    evidence=(
        result.range_summary.preprocess_id,
        f"范围 {start_date} 至 {end_date}",
        f"覆盖率 {result.range_summary.coverage_ratio:.1%}",
    ),
    next_step="结合覆盖率、样本数和质量说明解释图表，不把相关性写成因果。",
)

st.write("")
render_section_heading(
    title="核心指标",
    description="峰值和均值使用 kW；累计电量使用现有 Wh 能量字段求和后转换为 kWh。",
)
_render_kpis(result)

st.write("")
render_section_heading(
    title="历史趋势",
    description=(
        f"当前图表 {len(result.trend):,} 个点，上限 {context.settings.ui.max_chart_points:,}；"
        "缺失点保持断线，不做前向填充。"
    ),
)
st.plotly_chart(_trend_figure(result), width="stretch", theme="streamlit")

st.write("")
render_section_heading(
    title="周期规律",
    description="每个桶都携带有效样本数、总样本数和覆盖率；工作日为星期一至星期五。",
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
    description="厨房、洗衣房、热水器/空调和未分项均使用真实能量字段，统一显示为 kWh。",
)
_render_submeter(result)

st.write("")
render_section_heading(
    title="确定性摘要与限制",
    description="每句话都可追溯到当前结果字段；没有调用 LLM，也没有预测未来。",
)
render_status_panel(
    tone="attention" if result.status == "attention" else "information",
    label="证据摘要",
    title="当前数据范围内观察到的事实",
    description="以下内容由本地规则生成，不表达未经数据支持的因果关系。",
    evidence=result.evidence,
    next_step="M4 将单独实现并验证模型训练与未来预测；本页不会提前展示相关结果。",
)
