"""M2 built-in data validation and preprocessing center."""

from __future__ import annotations

import pandas as pd
import streamlit as st

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
    missing_rate = report.measurement_missing_row_count / row_count if row_count else 0.0

    st.subheader("数据质量摘要")
    first = st.columns(4)
    first[0].metric("记录数", f"{row_count:,}")
    first[1].metric("字段数", field_count)
    first[2].metric("采样频率", cadence)
    first[3].metric("质量状态", report.status)
    second = st.columns(4)
    second[0].metric("缺失测量行", f"{report.measurement_missing_row_count:,}")
    second[1].metric("缺失率", f"{missing_rate:.4%}")
    second[2].metric("缺失区段", len(report.missing_blocks))
    second[3].metric("最长缺失", f"{longest.length_minutes if longest else 0:,} 分钟")
    third = st.columns(4)
    third[0].metric("阻断", report.issue_count("error"))
    third[1].metric("警告", report.issue_count("warning"))
    third[2].metric("信息", report.issue_count("information"))
    third[3].metric("质量评分", f"{report.score:.2f}" if report.score is not None else "未评分")
    st.caption(f"时间范围：{start_time} 至 {end_time}；时间为数据集本地朴素时间。")

    if report.missing_blocks:
        st.subheader("缺失区段")
        block_rows = [
            {
                "开始": block.start_time,
                "结束": block.end_time,
                "分钟数": block.length_minutes,
            }
            for block in report.missing_blocks
        ]
        st.dataframe(pd.DataFrame(block_rows), hide_index=True, use_container_width=True)
    if report.issues:
        with st.expander("质量问题与修复建议"):
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
                use_container_width=True,
            )


context = _get_context()
service = DataService(context)
state = service.inspect_builtin_state()

st.title("数据中心")
st.caption("M2 数据闭环：只读校验内置 CSV，并按配置生成可重复 Parquet 与 manifest。")

if not state.source_exists:
    st.error(f"内置 CSV 不存在：{state.source_path_alias}")
    st.info("请恢复课程提供的原始 CSV；不要创建空文件或修改配置来绕过校验。")
    st.stop()

st.success(f"内置 CSV 可用：{state.source_path_alias}")
st.write("**SHA-256（可复制）：**")
st.code(state.sha256 or "读取失败", language=None)
if state.error:
    st.error(f"现有处理状态不可用：{state.error}")

validate_col, prepare_col = st.columns(2)
validate_clicked = validate_col.button("运行完整质量校验", use_container_width=True)
prepare_clicked = prepare_col.button("生成 / 重建 M2 处理产物", use_container_width=True)

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
    st.info("尚未运行完整质量校验。点击上方按钮后才会解析全部数据。")
else:
    _render_quality(dataset, report, manifest)

if manifest is None or not state.processed_exists and not prepare_clicked:
    st.subheader("预处理产物")
    st.info("尚未生成可用的 15 分钟处理产物；当前没有预测、预警或模型结果。")
else:
    split_counts = manifest.splits["counts"]
    st.subheader("预处理产物")
    columns = st.columns(4)
    columns[0].metric("15 分钟点数", f"{sum(split_counts.values()):,}")
    columns[1].metric("训练集", f"{split_counts['train']:,}")
    columns[2].metric("验证集", f"{split_counts['validation']:,}")
    columns[3].metric("测试集", f"{split_counts['test']:,}")
    st.write(f"**Manifest：** `{manifest.artifacts['manifest']}`")
    try:
        preview = service.load_processed_preview(manifest, rows=12)
        st.subheader("15 分钟数据预览（最多 12 行）")
        st.dataframe(preview, hide_index=True, use_container_width=True)
    except OSError as exc:
        st.error(f"处理数据文件不可读：{exc}")

st.warning("M2 不训练模型、不生成预测指标，也不调用任何外部大模型 API。")
