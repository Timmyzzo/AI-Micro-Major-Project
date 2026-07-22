"""Public dataset overview and one-step data preparation."""

from __future__ import annotations

import streamlit as st

from app.components.layout import (
    render_fact_list,
    render_page_header,
    render_section_heading,
    render_status_panel,
)
from powerinsight.schemas import DatasetManifest
from powerinsight.services.data_service import DataService
from powerinsight.services.runtime import RuntimeContext

DATASET_NAME = "Individual Household Electric Power Consumption"
DATASET_SOURCE = "UCI Machine Learning Repository"
DATASET_URL = (
    "https://archive.ics.uci.edu/dataset/235/individual+household+electric+power+consumption"
)


def _get_context() -> RuntimeContext:
    context = st.session_state.get("runtime_context")
    if not isinstance(context, RuntimeContext):
        st.error("系统尚未初始化，请从应用入口启动。")
        st.stop()
    return context


def _safe_error(exc: Exception, context: RuntimeContext) -> str:
    return str(exc).replace(str(context.paths.root), ".")


context = _get_context()
service = DataService(context)
state = service.inspect_builtin_state()

render_page_header(
    eyebrow="公开数据集",
    title="数据中心",
    description="查看当前系统使用的数据来源、时间范围和数据规模。",
    badge="UCI 数据集",
)

render_section_heading(title="数据来源")
source_col, link_col = st.columns((3, 1), vertical_alignment="bottom")
with source_col:
    render_fact_list(
        (
            ("数据集", DATASET_NAME),
            ("来源", DATASET_SOURCE),
            ("采集对象", "法国 Sceaux 一户家庭的分钟级用电记录"),
            ("主要字段", "总有功功率、电压、电流与三项分表电量"),
        )
    )
with link_col:
    st.link_button(
        "查看数据集来源",
        DATASET_URL,
        icon=":material/open_in_new:",
        width="stretch",
    )

if not state.source_exists:
    render_status_panel(
        tone="blocked",
        label="数据状态",
        title="数据文件不可用",
        description="请恢复项目数据文件后刷新页面。",
    )
    st.stop()

manifest: DatasetManifest | None = state.manifest if state.processed_exists else None
if manifest is None:
    st.write("")
    render_status_panel(
        tone="attention",
        label="数据状态",
        title="分析数据尚未准备",
        description="点击一次即可生成用电分析和负荷预测需要的数据。",
    )
    if st.button(
        "准备分析数据",
        type="primary",
        icon=":material/database:",
        width="stretch",
    ):
        try:
            with st.spinner("正在准备分析数据……"):
                pipeline = service.prepare_builtin()
            manifest = pipeline.manifest
            st.success("分析数据已准备完成。")
        except Exception as exc:
            st.error(f"数据准备失败：{_safe_error(exc, context)}")

if manifest is None:
    st.stop()

quality = manifest.quality_report
processed_points = sum(manifest.splits["counts"].values())
coverage = 1.0 - (
    quality.measurement_missing_row_count / manifest.source_rows if manifest.source_rows else 0.0
)

st.write("")
render_section_heading(title="数据概览")
overview = st.columns(4)
overview[0].metric("原始记录", f"{manifest.source_rows:,}")
overview[1].metric("时间范围", f"{manifest.start_time:%Y-%m} 至 {manifest.end_time:%Y-%m}")
overview[2].metric("分析数据点", f"{processed_points:,}")
overview[3].metric("有效数据覆盖率", f"{coverage:.2%}")

details = st.columns(3)
details[0].metric("原始采样频率", "1 分钟")
details[1].metric("分析粒度", "15 分钟")
details[2].metric("缺失区段", len(quality.missing_blocks))

st.write("")
render_section_heading(title="数据示例")
try:
    preview = service.load_processed_preview(manifest, rows=10)
    columns = [
        column
        for column in (
            "timestamp",
            "global_active_power_kw",
            "voltage_v",
            "global_intensity_a",
            "split",
        )
        if column in preview.columns
    ]
    display = preview[columns].rename(
        columns={
            "timestamp": "时间",
            "global_active_power_kw": "总有功功率（kW）",
            "voltage_v": "电压（V）",
            "global_intensity_a": "电流（A）",
            "split": "数据用途",
        }
    )
    if "数据用途" in display.columns:
        display["数据用途"] = display["数据用途"].map(
            {"train": "训练", "validation": "验证", "test": "测试"}
        )
    st.dataframe(display, hide_index=True, width="stretch")
except OSError as exc:
    st.error(f"数据示例读取失败：{_safe_error(exc, context)}")
