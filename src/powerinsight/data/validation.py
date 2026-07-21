"""Vectorized CSV parsing and deterministic data-quality reporting."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd  # type: ignore[import-untyped]

from powerinsight.data.catalog import DATA_SCHEMA_VERSION, build_dataset_id, compute_sha256
from powerinsight.schemas import DataIssue, DataQualityReport, DatasetRecord, MissingBlock

VALIDATION_VERSION = "1.0"
RAW_COLUMN_MAP: dict[str, str] = {
    "index": "row_index",
    "Date": "date",
    "Time": "time",
    "Global_active_power": "global_active_power_kw",
    "Global_reactive_power": "global_reactive_power_kw",
    "Voltage": "voltage_v",
    "Global_intensity": "global_intensity_a",
    "Sub_metering_1": "sub_metering_1_wh",
    "Sub_metering_2": "sub_metering_2_wh",
    "Sub_metering_3": "sub_metering_3_wh",
}
MEASUREMENT_COLUMNS: tuple[str, ...] = (
    "global_active_power_kw",
    "global_reactive_power_kw",
    "voltage_v",
    "global_intensity_a",
    "sub_metering_1_wh",
    "sub_metering_2_wh",
    "sub_metering_3_wh",
)
MISSING_TOKENS = frozenset(("", "?", "na", "nan", "none", "null"))
DEFAULT_CADENCE = pd.Timedelta(minutes=1)


class DataValidationError(ValueError):
    """Raised for a blocking source schema or parsing defect."""


@dataclass(frozen=True)
class ValidationResult:
    """Verified source metadata, report, and normalized minute frame."""

    dataset: DatasetRecord
    report: DataQualityReport
    frame: pd.DataFrame


def validate_csv(
    path: Path,
    *,
    path_alias: str,
    name: str = "家庭用电内置数据",
    source_type: Literal["built_in", "upload"] = "built_in",
    expected_sha256: str | None = None,
    raw_cadence: str = "1min",
    short_gap_max_minutes: int = 60,
) -> ValidationResult:
    """Read and validate one CSV while preserving the source file unchanged."""
    if not path.is_file():
        raise DataValidationError(f"DATA_SOURCE_NOT_FOUND: 找不到数据文件 {path_alias}")
    header = _read_header(path)
    _validate_header(header)
    sha256 = compute_sha256(path)
    if expected_sha256 is not None and sha256 != expected_sha256.upper():
        raise DataValidationError(
            "DATA_FINGERPRINT_MISMATCH: 原始文件 SHA-256 与配置不一致，请恢复受信任文件"
        )
    raw_frame = pd.read_csv(path, dtype=str, keep_default_na=False, na_filter=False)
    return validate_frame(
        raw_frame,
        path_alias=path_alias,
        name=name,
        source_type=source_type,
        sha256=sha256,
        size_bytes=path.stat().st_size,
        raw_cadence=raw_cadence,
        short_gap_max_minutes=short_gap_max_minutes,
    )


def validate_frame(
    raw_frame: pd.DataFrame,
    *,
    path_alias: str = "memory:test.csv",
    name: str = "测试数据",
    source_type: Literal["built_in", "upload"] = "upload",
    sha256: str = "0" * 64,
    size_bytes: int = 0,
    raw_cadence: str = "1min",
    short_gap_max_minutes: int = 60,
) -> ValidationResult:
    """Normalize and validate a raw frame without modifying the caller's DataFrame."""
    _validate_header([str(column) for column in raw_frame.columns])
    frame, invalid_numeric_count, was_out_of_order = _normalize_frame(raw_frame)
    row_count = len(frame)
    if row_count == 0:
        raise DataValidationError("DATA_EMPTY: 数据文件不包含记录")
    timestamp_failures = int(frame["timestamp"].isna().sum())
    if timestamp_failures:
        raise DataValidationError(
            f"DATA_TIMESTAMP_INVALID: {timestamp_failures} 行日期或时间无法按 day-first 规则解析"
        )
    if not frame["global_active_power_kw"].notna().any():
        raise DataValidationError("DATA_TARGET_INVALID: 总有功功率列没有任何有效数值")

    frame = frame.sort_values("timestamp", kind="stable").reset_index(drop=True)
    timestamps = frame["timestamp"]
    duplicate_count = int(timestamps.duplicated().sum())
    cadence = pd.Timedelta(raw_cadence)
    unique_differences = timestamps.drop_duplicates().diff().dropna()
    cadence_violations = int(unique_differences.ne(cadence).sum())
    inferred_cadence = _infer_cadence(unique_differences, fallback=raw_cadence)
    missing_cells = {column: int(frame[column].isna().sum()) for column in MEASUREMENT_COLUMNS}
    missing_mask = frame.loc[:, MEASUREMENT_COLUMNS].isna().any(axis=1)
    measurement_missing_rows = int(missing_mask.sum())
    missing_blocks = find_missing_blocks(frame, missing_mask=missing_mask, cadence=cadence)
    issues = _build_issues(
        missing_cells=missing_cells,
        missing_blocks=missing_blocks,
        invalid_numeric_count=invalid_numeric_count,
        duplicate_count=duplicate_count,
        cadence_violations=cadence_violations,
        was_out_of_order=was_out_of_order,
        short_gap_max_minutes=short_gap_max_minutes,
    )
    score = _quality_score(
        row_count=row_count,
        missing_cells=sum(missing_cells.values()),
        invalid_numeric_count=invalid_numeric_count,
        duplicate_count=duplicate_count,
        cadence_violations=cadence_violations,
    )
    status: Literal["usable", "attention", "blocked"] = (
        "attention" if any(issue.severity == "warning" for issue in issues) else "usable"
    )
    now = datetime.now(UTC)
    dataset_id = build_dataset_id(path_alias, sha256)
    dataset = DatasetRecord(
        schema_version=DATA_SCHEMA_VERSION,
        dataset_id=dataset_id,
        name=name,
        source_type=source_type,
        path_alias=path_alias,
        sha256=sha256.upper(),
        size_bytes=size_bytes,
        row_count=row_count,
        field_count=len(raw_frame.columns),
        start_time=timestamps.iloc[0].to_pydatetime(),
        end_time=timestamps.iloc[-1].to_pydatetime(),
        cadence=inferred_cadence,
        status="validated",
        created_at=now,
    )
    report = DataQualityReport(
        dataset_id=dataset_id,
        validation_version=VALIDATION_VERSION,
        status=status,
        score=score,
        row_count=row_count,
        parsed_timestamp_count=row_count,
        duplicate_count=duplicate_count,
        cadence_violations=cadence_violations,
        missing_cells_by_column=missing_cells,
        measurement_missing_row_count=measurement_missing_rows,
        missing_blocks=missing_blocks,
        issues=issues,
        generated_at=now,
    )
    return ValidationResult(dataset=dataset, report=report, frame=frame)


def find_missing_blocks(
    frame: pd.DataFrame,
    *,
    missing_mask: pd.Series | None = None,
    cadence: pd.Timedelta = DEFAULT_CADENCE,
) -> tuple[MissingBlock, ...]:
    """Return consecutive measurement-missing blocks from a timestamp-sorted frame."""
    if frame.empty:
        return ()
    ordered_index = frame.sort_values("timestamp", kind="stable").index
    ordered = frame.loc[ordered_index].reset_index(drop=True)
    mask = (
        ordered.loc[:, MEASUREMENT_COLUMNS].isna().any(axis=1)
        if missing_mask is None
        else missing_mask.loc[ordered_index].reset_index(drop=True).astype(bool)
    )
    previous_missing = mask.shift(fill_value=False)
    cadence_break = ordered["timestamp"].diff().ne(cadence)
    starts = mask & (~previous_missing | cadence_break)
    block_ids = starts.cumsum()
    missing_rows = ordered.loc[mask, ["timestamp", *MEASUREMENT_COLUMNS]].copy()
    if missing_rows.empty:
        return ()
    missing_rows["block_id"] = block_ids.loc[mask].to_numpy()
    blocks: list[MissingBlock] = []
    for _, group in missing_rows.groupby("block_id", sort=True):
        columns = tuple(column for column in MEASUREMENT_COLUMNS if group[column].isna().any())
        blocks.append(
            MissingBlock(
                start_time=group["timestamp"].iloc[0].to_pydatetime(),
                end_time=group["timestamp"].iloc[-1].to_pydatetime(),
                length_minutes=len(group),
                missing_columns=columns,
            )
        )
    return tuple(blocks)


def _read_header(path: Path) -> list[str]:
    try:
        with path.open("r", encoding="utf-8", newline="") as file_handle:
            return next(csv.reader(file_handle))
    except (OSError, StopIteration, UnicodeError, csv.Error) as exc:
        raise DataValidationError(f"DATA_HEADER_UNREADABLE: 无法读取 CSV 表头: {exc}") from exc


def _validate_header(header: list[str]) -> None:
    if len(header) != len(set(header)):
        raise DataValidationError("DATA_SCHEMA_DUPLICATE_COLUMN: CSV 存在重复字段名")
    missing = [column for column in RAW_COLUMN_MAP if column not in header]
    if missing:
        raise DataValidationError(f"DATA_SCHEMA_MISSING_COLUMN: 缺少必需字段: {', '.join(missing)}")


def _normalize_frame(raw_frame: pd.DataFrame) -> tuple[pd.DataFrame, int, bool]:
    frame = raw_frame.rename(columns=RAW_COLUMN_MAP).copy(deep=True)
    combined = (
        frame["date"].astype("string").str.strip()
        + " "
        + frame["time"].astype("string").str.strip()
    )
    timestamps = pd.to_datetime(combined, format="%d/%m/%y %H:%M:%S", errors="coerce")
    long_year_mask = timestamps.isna()
    if long_year_mask.any():
        timestamps.loc[long_year_mask] = pd.to_datetime(
            combined.loc[long_year_mask],
            format="%d/%m/%Y %H:%M:%S",
            errors="coerce",
        )
    frame["timestamp"] = timestamps
    invalid_numeric_count = 0
    for column in MEASUREMENT_COLUMNS:
        cleaned = frame[column].astype("string").str.strip()
        missing_tokens = cleaned.str.lower().isin(MISSING_TOKENS)
        parsed = pd.to_numeric(cleaned.mask(missing_tokens), errors="coerce")
        non_finite = pd.Series(np.isinf(parsed.to_numpy(dtype=float, na_value=np.nan)))
        invalid_numeric_count += int((parsed.isna() & ~missing_tokens).sum() + non_finite.sum())
        frame[column] = parsed.replace((np.inf, -np.inf), np.nan).astype(float)
    frame["row_index"] = pd.to_numeric(frame["row_index"], errors="coerce").astype("Int64")
    was_out_of_order = not frame["timestamp"].is_monotonic_increasing
    normalized = frame.loc[:, ["row_index", "timestamp", *MEASUREMENT_COLUMNS]]
    return normalized, invalid_numeric_count, was_out_of_order


def _infer_cadence(differences: pd.Series, *, fallback: str) -> str:
    if differences.empty:
        return fallback
    mode = differences.mode()
    if mode.empty:
        return fallback
    value = pd.Timedelta(mode.iloc[0])
    if value == pd.Timedelta(minutes=1):
        return "1min"
    return str(value)


def _build_issues(
    *,
    missing_cells: dict[str, int],
    missing_blocks: tuple[MissingBlock, ...],
    invalid_numeric_count: int,
    duplicate_count: int,
    cadence_violations: int,
    was_out_of_order: bool,
    short_gap_max_minutes: int,
) -> tuple[DataIssue, ...]:
    issues: list[DataIssue] = [
        DataIssue(
            code="DATA_FIELDS_MAPPED",
            severity="information",
            message="原始字段已映射为带单位的稳定内部字段。",
            count=len(RAW_COLUMN_MAP),
            suggested_action="无需操作；后续处理只使用内部字段名。",
        )
    ]
    missing_count = sum(missing_cells.values())
    if missing_count:
        issues.append(
            DataIssue(
                code="DATA_MEASUREMENT_MISSING",
                severity="warning",
                message="测量字段存在缺失值，缺失值保留为 NaN。",
                count=missing_count,
                suggested_action="运行预处理；短缺失可插值，长缺失必须保留。",
            )
        )
    long_blocks = [
        block for block in missing_blocks if block.length_minutes > short_gap_max_minutes
    ]
    if long_blocks:
        longest = max(long_blocks, key=lambda block: block.length_minutes)
        issues.append(
            DataIssue(
                code="DATA_LONG_MISSING_BLOCK",
                severity="warning",
                message=(
                    f"发现 {len(long_blocks)} 个超过 {short_gap_max_minutes} 分钟的长缺失区段。"
                ),
                count=len(long_blocks),
                start_time=longest.start_time,
                end_time=longest.end_time,
                suggested_action="不要跨段插值；后续窗口必须排除受影响区间。",
            )
        )
    if invalid_numeric_count:
        issues.append(
            DataIssue(
                code="DATA_NUMERIC_INVALID",
                severity="warning",
                message="无法解析或非有限的测量值已转换为 NaN。",
                count=invalid_numeric_count,
                suggested_action="检查源字段格式，不要把无效值填为 0。",
            )
        )
    if duplicate_count:
        issues.append(
            DataIssue(
                code="DATA_TIMESTAMP_DUPLICATE",
                severity="warning",
                message="存在重复时间戳。",
                count=duplicate_count,
                suggested_action="在进入聚合前确认并处理重复记录。",
            )
        )
    if cadence_violations:
        issues.append(
            DataIssue(
                code="DATA_CADENCE_VIOLATION",
                severity="warning",
                message="时间戳未完全遵循配置的原始采样间隔。",
                count=cadence_violations,
                suggested_action="检查断点、重复或异常时间戳。",
            )
        )
    if was_out_of_order:
        issues.append(
            DataIssue(
                code="DATA_TIMESTAMP_SORTED",
                severity="information",
                message="输入记录不是时间升序，校验结果已使用稳定排序。",
                suggested_action="建议源文件按时间升序保存。",
            )
        )
    return tuple(issues)


def _quality_score(
    *,
    row_count: int,
    missing_cells: int,
    invalid_numeric_count: int,
    duplicate_count: int,
    cadence_violations: int,
) -> float:
    measurement_cells = max(row_count * len(MEASUREMENT_COLUMNS), 1)
    time_intervals = max(row_count - 1, 1)
    completeness = max(0.0, 1.0 - missing_cells / measurement_cells)
    numeric_validity = max(0.0, 1.0 - invalid_numeric_count / measurement_cells)
    uniqueness = max(0.0, 1.0 - duplicate_count / row_count)
    cadence = max(0.0, 1.0 - cadence_violations / time_intervals)
    return round(
        completeness * 35.0 + numeric_validity * 25.0 + uniqueness * 20.0 + cadence * 20.0,
        4,
    )
