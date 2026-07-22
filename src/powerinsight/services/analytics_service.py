"""Read-only service for deterministic analytics over prepared data."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Literal, cast

import pandas as pd  # type: ignore[import-untyped]
import pyarrow.parquet as pq

from powerinsight.analytics import AnalyticsResult, analyze_frame
from powerinsight.paths import display_path
from powerinsight.schemas import DatasetManifest
from powerinsight.services.data_service import DataService
from powerinsight.services.runtime import RuntimeContext

REQUIRED_COLUMNS: tuple[str, ...] = (
    "timestamp",
    "global_active_power_kw",
    "global_active_energy_wh",
    "sub_metering_1_wh",
    "sub_metering_2_wh",
    "sub_metering_3_wh",
    "unmetered_energy_wh",
    "missing_ratio",
    "imputed_ratio",
    "long_gap",
)


@dataclass(frozen=True)
class AnalyticsAvailability:
    """Low-cost, display-safe state for the analytics dependency chain."""

    status: Literal["ready", "blocked"]
    manifest: DatasetManifest | None
    start_time: datetime | None
    end_time: datetime | None
    title: str
    reason: str
    evidence: tuple[str, ...]
    next_step: str


class AnalyticsError(RuntimeError):
    """Display-safe analytics failure with stable remediation fields."""

    def __init__(
        self,
        *,
        code: str,
        title: str,
        reason: str,
        evidence: tuple[str, ...],
        next_step: str,
    ) -> None:
        super().__init__(reason)
        self.code = code
        self.title = title
        self.reason = reason
        self.evidence = evidence
        self.next_step = next_step


class AnalyticsService:
    """Validate prepared data, read required columns, and run pure analysis."""

    def __init__(self, context: RuntimeContext) -> None:
        self._context = context

    def inspect_availability(self) -> AnalyticsAvailability:
        """Validate current manifest and Parquet identity without exposing local paths."""
        try:
            manifest, processed_path = self._validated_artifact()
            frame = _read_processed_cached(
                str(processed_path),
                manifest.preprocess_id,
                processed_path.stat().st_mtime_ns,
            )
            if frame.empty:
                raise AnalyticsError(
                    code="ANALYTICS_EMPTY_ARTIFACT",
                    title="处理数据为空",
                    reason="分析数据中没有可用的 15 分钟记录。",
                    evidence=(manifest.preprocess_id,),
                    next_step="在数据中心重新准备分析数据。",
                )
            start_time = _as_datetime(frame["timestamp"].min())
            end_time = _as_datetime(frame["timestamp"].max())
            return AnalyticsAvailability(
                status="ready",
                manifest=manifest,
                start_time=start_time,
                end_time=end_time,
                title="分析数据可用",
                reason="15 分钟用电数据已准备完成。",
                evidence=(
                    manifest.dataset_id,
                    manifest.preprocess_id,
                    f"15 分钟点数 {len(frame):,}",
                ),
                next_step="选择日期范围查看用电分析。",
            )
        except AnalyticsError as exc:
            return AnalyticsAvailability(
                status="blocked",
                manifest=None,
                start_time=None,
                end_time=None,
                title=exc.title,
                reason=exc.reason,
                evidence=(exc.code, *exc.evidence),
                next_step=exc.next_step,
            )

    def analyze(self, *, start: datetime, end_exclusive: datetime) -> AnalyticsResult:
        """Return one cached-read, deterministic analysis for a half-open time range."""
        manifest, processed_path = self._validated_artifact()
        try:
            frame = _read_processed_cached(
                str(processed_path),
                manifest.preprocess_id,
                processed_path.stat().st_mtime_ns,
            )
            return analyze_frame(
                frame,
                preprocess_id=manifest.preprocess_id,
                start=start,
                end_exclusive=end_exclusive,
                max_chart_points=self._context.settings.ui.max_chart_points,
                source_negative_unmetered_records=_negative_unmetered_rows(manifest),
            )
        except AnalyticsError:
            raise
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise AnalyticsError(
                code="ANALYTICS_QUERY_FAILED",
                title="用电分析执行失败",
                reason="处理数据已定位，但所选范围的只读查询或确定性计算失败。",
                evidence=(type(exc).__name__, manifest.preprocess_id),
                next_step="复核日期范围；若仍失败，在数据中心重新准备分析数据。",
            ) from exc

    def _validated_artifact(self) -> tuple[DatasetManifest, Path]:
        state = DataService(self._context).inspect_builtin_state()
        if state.error:
            raise AnalyticsError(
                code="ANALYTICS_MANIFEST_IDENTITY_MISMATCH",
                title="数据身份不一致",
                reason="当前数据文件与已有分析数据不一致。",
                evidence=tuple(item for item in (state.dataset_id,) if item),
                next_step="在数据中心重新准备分析数据。",
            )
        if state.manifest is None:
            raise AnalyticsError(
                code="ANALYTICS_MANIFEST_MISSING",
                title="分析数据尚未准备",
                reason="当前没有可用于分析的 15 分钟用电数据。",
                evidence=tuple(item for item in (state.dataset_id,) if item),
                next_step="前往数据中心准备分析数据。",
            )
        manifest = state.manifest
        if manifest.schema_version != "1.0" or manifest.cadence.get("processed") != "15min":
            raise AnalyticsError(
                code="ANALYTICS_MANIFEST_INCOMPATIBLE",
                title="分析数据版本不兼容",
                reason="当前分析数据需要使用最新版本重新生成。",
                evidence=(manifest.schema_version, str(manifest.cadence.get("processed"))),
                next_step="在数据中心重新准备分析数据。",
            )
        missing_contract = tuple(
            column for column in REQUIRED_COLUMNS if column not in manifest.columns
        )
        if missing_contract:
            raise AnalyticsError(
                code="ANALYTICS_MANIFEST_COLUMNS_MISSING",
                title="分析字段不完整",
                reason="当前数据缺少用电分析所需字段。",
                evidence=missing_contract,
                next_step="在数据中心重新准备分析数据。",
            )
        processed_path = (
            self._context.paths.data_dir
            / "processed"
            / manifest.preprocess_id
            / "power_15min.parquet"
        )
        expected_alias = display_path(processed_path, root=self._context.paths.root)
        if manifest.artifacts.get("processed") != expected_alias:
            raise AnalyticsError(
                code="ANALYTICS_ARTIFACT_ALIAS_MISMATCH",
                title="处理产物身份不一致",
                reason="当前分析数据文件与记录不一致。",
                evidence=(manifest.preprocess_id,),
                next_step="在数据中心重新准备分析数据。",
            )
        if not processed_path.is_file():
            raise AnalyticsError(
                code="ANALYTICS_PARQUET_MISSING",
                title="15 分钟处理数据缺失",
                reason="15 分钟分析数据文件不可用。",
                evidence=(manifest.preprocess_id,),
                next_step="在数据中心重新准备分析数据。",
            )
        try:
            parquet = pq.ParquetFile(processed_path)  # type: ignore[no-untyped-call]
        except (OSError, ValueError) as exc:
            raise AnalyticsError(
                code="ANALYTICS_PARQUET_UNREADABLE",
                title="15 分钟处理数据不可读",
                reason="15 分钟分析数据无法读取。",
                evidence=(type(exc).__name__, manifest.preprocess_id),
                next_step="在数据中心重新准备分析数据。",
            ) from exc
        missing_parquet = tuple(
            column for column in REQUIRED_COLUMNS if column not in parquet.schema_arrow.names
        )
        if missing_parquet:
            raise AnalyticsError(
                code="ANALYTICS_PARQUET_COLUMNS_MISSING",
                title="15 分钟处理数据字段不兼容",
                reason="分析数据缺少用电分析所需字段。",
                evidence=missing_parquet,
                next_step="在数据中心重新准备分析数据。",
            )
        split_counts = manifest.splits.get("counts")
        if not isinstance(split_counts, dict):
            raise AnalyticsError(
                code="ANALYTICS_MANIFEST_SPLITS_INVALID",
                title="分析数据不完整",
                reason="分析数据的训练、验证和测试范围信息缺失。",
                evidence=(manifest.preprocess_id,),
                next_step="在数据中心重新准备分析数据。",
            )
        expected_rows = 0
        for value in split_counts.values():
            if not isinstance(value, int):
                raise AnalyticsError(
                    code="ANALYTICS_MANIFEST_SPLITS_INVALID",
                    title="分析数据不完整",
                    reason="分析数据的范围计数无效。",
                    evidence=(manifest.preprocess_id,),
                    next_step="在数据中心重新准备分析数据。",
                )
            expected_rows += value
        if parquet.metadata.num_rows != expected_rows:
            raise AnalyticsError(
                code="ANALYTICS_PARQUET_ROW_COUNT_MISMATCH",
                title="15 分钟处理数据身份不一致",
                reason="分析数据行数与范围计数不一致。",
                evidence=(f"manifest={expected_rows}", f"parquet={parquet.metadata.num_rows}"),
                next_step="在数据中心重新准备分析数据。",
            )
        return manifest, processed_path


@lru_cache(maxsize=4)
def _read_processed_cached(
    processed_path: str,
    preprocess_id: str,
    modified_time_ns: int,
) -> pd.DataFrame:
    """Read only required columns; identity and mtime form the in-process cache key."""
    del preprocess_id, modified_time_ns
    frame = pd.read_parquet(processed_path, columns=list(REQUIRED_COLUMNS))
    timestamps = pd.to_datetime(frame["timestamp"], errors="coerce")
    if timestamps.isna().any():
        raise ValueError("processed timestamp column contains unparseable values")
    if timestamps.dt.tz is not None:
        raise ValueError("processed timestamps must remain dataset-local naive time")
    result = frame.copy(deep=True)
    result["timestamp"] = timestamps
    return result.sort_values("timestamp", kind="stable").reset_index(drop=True)


def clear_analytics_cache() -> None:
    """Clear the small process-local Parquet cache for isolated tests and rebuilds."""
    _read_processed_cached.cache_clear()


def _as_datetime(value: object) -> datetime | None:
    if pd.isna(value):
        return None
    return cast(datetime, pd.Timestamp(value).to_pydatetime())


def _negative_unmetered_rows(manifest: DatasetManifest) -> int:
    value = manifest.preprocessing.get("negative_unmetered_rows", 0)
    return value if isinstance(value, int) and value >= 0 else 0
