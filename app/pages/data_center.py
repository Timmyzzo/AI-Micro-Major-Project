"""M2 built-in data validation and preprocessing center."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from app.components.layout import (
    render_page_header,
    render_section_heading,
    render_status_panel,
)
from powerinsight.schemas import DataQualityReport, DatasetManifest, DatasetRecord
from powerinsight.services.data_service import DataService
from powerinsight.services.runtime import RuntimeContext

SESSION_DATASET = "m2_dataset_record"
SESSION_REPORT = "m2_quality_report"
SESSION_MANIFEST = "m2_manifest"


def _get_context() -> RuntimeContext:
    context = st.session_state.get("runtime_context")
    if not isinstance(context, RuntimeContext):
        st.error("运行上下文尚未初始化，请从应用入口启动。")
        st.stop()
    return context


def _safe_error(exc: Exception, context: RuntimeContext) -> str:
    return str(exc).replace(str(context.paths.root), ".")


def _load_session_result() -> tuple[DatasetRecord | None, DataQualityReport | None]:
    dataset_json = st.session_state.get(SESSION_DATASET)
    report_json = st.session_state.get(SESSION_REPORT)
    dataset = (
        DatasetRecord.model_validate_json(dataset_json) if isinstance(dataset_json, str) else None
    )
    report = (
        DataQualityReport.model_validate_json(report_json) if isinstance(report_json, str) else None
    )
    return dataset, report


def _render_quality(
    dataset: DatasetRecord | None,
    report: DataQualityReport,
    manifest: DatasetManifest | None,
) -> None:
    row_count = (
        dataset.row_count if dataset else manifest.source_rows if manifest else report.row_count
    )
    field_count = dataset.field_count if dataset else manifest.source_fields if manifest else 0
    start_time = dataset.start_time if dataset else manifest.start_time if manifest else None
    end_time = dataset.end_time if dataset else manifest.end_time if manifest else None
    cadence = dataset.cadence if dataset else manifest.cadence["raw"] if manifest else "未知"
    longest = max(report.missing_blocks, key=lambda block: block.length_minutes, default=None)
    missing_rate = report.measurement_missing_row_count / row_count if row_count else None
    tone = (
        "success"
        if report.status == "usable"
        else "attention"
        if report.status == "attention"
        else "blocked"
    )
    status_title = {
        "usable": "数据质量可直接进入后续处理",
        "attention": "数据可用，但长缺失需要持续保留",
        "blocked": "数据质量存在阻断问题",
    }[report.status]
    status_description = {
        "usable": "已完成结构、时间、数值、缺失与频率检查，没有发现阻断后续处理的问题。",
        "attention": "质量报告允许继续处理，但相关页面必须显式呈现长缺失和派生字段警告。",
        "blocked": "至少一个错误会阻止后续处理；需要按问题建议修复后重新校验。",
    }[report.status]

    render_status_panel(
        tone=tone,
        label="质量状态",
        title=status_title,
        description=status_description,
        evidence=(
            f"缺失测量行 {report.measurement_missing_row_count:,}",
            f"缺失区段 {len(report.missing_blocks)}",
            f"问题 {len(report.issues)} 项",
        ),
        next_step="复核缺失区段和问题建议；只有用户主动操作才会重新校验或生成处理产物。",
    )

    st.write("")
    render_section_heading(
        title="数据轮廓",
        description="基础身份与时间范围来自真实校验或 manifest。",
    )
    first = st.columns(4)
    first[0].metric("记录数", f"{row_count:,}")
    first[1].metric("字段数", field_count if field_count else "—")
    first[2].metric("采样频率", cadence)
    first[3].metric("质量评分", f"{report.score:.2f}" if report.score is not None else "未评分")
    st.caption(f"时间范围：{start_time} 至 {end_time}；时间为数据集本地朴素时间。")

    render_section_heading(
        title="缺失与问题证据",
        description="缺失不会被显示成 0，长缺失也不会被跨段插值。",
    )
    second = st.columns(4)
    second[0].metric("缺失测量行", f"{report.measurement_missing_row_count:,}")
    second[1].metric("缺失率", f"{missing_rate:.4%}" if missing_rate is not None else "—")
    second[2].metric("缺失区段", len(report.missing_blocks))
    second[3].metric("最长缺失", f"{longest.length_minutes:,} 分钟" if longest else "—")
    issue_columns = st.columns(3)
    issue_columns[0].metric("阻断问题", report.issue_count("error"))
    issue_columns[1].metric("警告问题", report.issue_count("warning"))
    issue_columns[2].metric("信息提示", report.issue_count("information"))

    if report.missing_blocks:
        render_section_heading(
            title="缺失区段",
            description="按时间边界和持续分钟数保留证据，表格采用高密度只读展示。",
        )
        block_rows = [
            {
                "开始": block.start_time,
                "结束": block.end_time,
                "分钟数": block.length_minutes,
            }
            for block in report.missing_blocks
        ]
        st.dataframe(pd.DataFrame(block_rows), hide_index=True, width="stretch")
    if report.issues:
        with st.expander("查看质量问题与修复建议", expanded=report.status == "blocked"):
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "级别": issue.severity,
                            "代码": issue.code,
                            "说明": issue.message,
                            "数量": issue.count,
                            "建议": issue.suggested_action,
                        }
                        for issue in report.issues
                    ]
                ),
                hide_index=True,
                width="stretch",
            )


context = _get_context()
service = DataService(context)
state = service.inspect_builtin_state()

render_page_header(
    eyebrow="M2 · 数据治理",
    title="数据中心",
    description=(
        "核对内置 CSV 身份，按用户明确操作运行完整质量校验，并生成可重复的 Parquet 与 manifest。"
    ),
    badge="原始数据只读",
)

if not state.source_exists:
    render_status_panel(
        tone="blocked",
        label="数据源状态",
        title="内置 CSV 不存在",
        description="课程提供的原始数据是 M2 与后续业务的只读基础，当前无法继续校验或处理。",
        evidence=(state.source_path_alias,),
        next_step="恢复课程提供的原始 CSV；不要创建空文件或修改配置来绕过校验。",
    )
    st.error(f"内置 CSV 不存在：{state.source_path_alias}")
    st.stop()

render_status_panel(
    tone="attention" if state.error else "ready",
    label="数据源状态",
    title="内置 CSV 身份可确认" if not state.error else "原始文件可用，现有处理状态需复核",
    description="此处只进行低成本文件身份检查；完整解析仍由下方按钮主动触发。",
    evidence=tuple(item for item in (state.dataset_id, state.source_path_alias) if item),
    next_step="先运行完整质量校验；仅在需要重建 M2 产物时再执行预处理。",
)
st.write("")
render_section_heading(
    title="完整数据指纹",
    description="使用代码块右上角复制按钮获取完整 SHA-256；页面不会截断指纹。",
)
st.code(state.sha256 or "读取失败", language=None)
if state.error:
    st.error(f"现有处理状态不可用：{state.error}")

render_section_heading(
    title="主动操作",
    description="两个操作都只在点击后执行；质量校验不会写原始 CSV，预处理会安全重建可再生产物。",
)
validate_col, prepare_col = st.columns(2)
validate_clicked = validate_col.button(
    "运行完整质量校验",
    type="primary",
    width="stretch",
    help="读取完整 CSV 并计算真实质量报告，不修改原始文件。",
)
prepare_clicked = prepare_col.button(
    "生成 / 重建 M2 处理产物",
    width="stretch",
    help="校验后生成分钟、15 分钟 Parquet 和 manifest；不训练模型。",
)

dataset, report = _load_session_result()
manifest = state.manifest
if validate_clicked:
    try:
        with st.spinner("正在读取 26 万行并计算真实质量状态……"):
            validation = service.validate_builtin(register=True)
        dataset, report = validation.dataset, validation.report
        st.session_state[SESSION_DATASET] = dataset.model_dump_json()
        st.session_state[SESSION_REPORT] = report.model_dump_json()
        st.success("完整质量校验已完成；原始 CSV 未被修改。")
    except Exception as exc:
        st.error(f"质量校验失败：{_safe_error(exc, context)}")
        st.info("请检查文件是否完整、字段是否齐全，以及日期是否符合日/月/年格式。")

if prepare_clicked:
    try:
        with st.spinner("正在执行缺失处理、派生字段、15 分钟聚合和固定切分……"):
            pipeline = service.prepare_builtin()
        dataset = pipeline.validation.dataset
        report = pipeline.manifest.quality_report
        manifest = pipeline.manifest
        st.session_state[SESSION_DATASET] = dataset.model_dump_json()
        st.session_state[SESSION_REPORT] = report.model_dump_json()
        st.session_state[SESSION_MANIFEST] = manifest.model_dump_json()
        st.success(
            "M2 处理完成："
            f"校验 {pipeline.timings.validation_seconds:.2f}s，"
            f"处理与写入 {pipeline.timings.preprocessing_write_seconds:.2f}s，"
            f"Parquet 回读 {pipeline.timings.parquet_read_seconds:.2f}s。"
        )
    except Exception as exc:
        st.error(f"预处理失败：{_safe_error(exc, context)}")
        st.info("失败运行会登记为 failed；修复源文件或配置后可安全重试。")

session_manifest = st.session_state.get(SESSION_MANIFEST)
if isinstance(session_manifest, str):
    manifest = DatasetManifest.model_validate_json(session_manifest)
if report is None and manifest is not None:
    report = manifest.quality_report

if report is None:
    render_status_panel(
        tone="empty",
        label="质量状态",
        title="尚未运行完整质量校验",
        description="页面目前只确认了文件身份，没有把未知缺失、问题或评分显示成 0。",
        evidence=("未解析 26 万行", "无自动计算", "原始文件保持只读"),
        next_step="点击“运行完整质量校验”后查看真实记录数、缺失区段和问题建议。",
    )
else:
    _render_quality(dataset, report, manifest)

processed_available = manifest is not None and (state.processed_exists or prepare_clicked)
st.write("")
render_section_heading(
    title="预处理产物",
    description="处理前后的状态保持在同一空间路径中，完成后显示身份、切分和小型预览。",
)
if not processed_available or manifest is None:
    render_status_panel(
        tone="empty",
        label="处理状态",
        title="尚未生成可用的 15 分钟处理产物",
        description=(
            "当前没有 manifest、训练窗口、预测、预警或模型结果，也不会在页面刷新时自动生成。"
        ),
        next_step="质量状态允许时，主动点击“生成 / 重建 M2 处理产物”。",
    )
else:
    split_counts = manifest.splits["counts"]
    render_status_panel(
        tone="success",
        label="处理状态",
        title="M2 处理产物可读取",
        description="15 分钟聚合、固定月份切分与 manifest 已建立稳定身份；这仍不是正式训练窗口。",
        evidence=(
            manifest.preprocess_id,
            f"15 分钟点数 {sum(split_counts.values()):,}",
            f"切分 {len(split_counts)} 组",
        ),
        next_step="复核切分和预览；M3 分析业务将在后续里程碑单独实现。",
    )
    columns = st.columns(4)
    columns[0].metric("15 分钟点数", f"{sum(split_counts.values()):,}")
    columns[1].metric("训练集", f"{split_counts['train']:,}")
    columns[2].metric("验证集", f"{split_counts['validation']:,}")
    columns[3].metric("测试集", f"{split_counts['test']:,}")
    st.caption(f"Manifest 别名：{manifest.artifacts['manifest']}")
    try:
        preview = service.load_processed_preview(manifest, rows=12)
        render_section_heading(
            title="15 分钟数据预览",
            description="只读取最多 12 行，页面不会重新加载或绘制全部 26 万条分钟记录。",
        )
        st.dataframe(preview, hide_index=True, width="stretch")
    except OSError as exc:
        st.error(f"处理数据文件不可读：{exc}")

st.write("")
render_status_panel(
    tone="disabled",
    label="M2 安全边界",
    title="数据治理止于可追踪处理产物",
    description="本页不训练模型、不生成预测或预警指标，也不调用任何外部大模型 API。",
    evidence=("原始 CSV 只读", "无模型训练", "无外部 API"),
)
