"""Read-only service for deterministic M3 analytics over M2 artifacts."""

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
    """Low-cost, display-safe state for the current M3 dependency chain."""

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
    """Validate M2 identity, read required Parquet columns, and run pure analysis."""

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
                    reason="M2 Parquet 可读取，但没有任何 15 分钟记录。",
                    evidence=(manifest.preprocess_id,),
                    next_step="在数据中心重新生成 M2 处理产物并复核记录数。",
                )
            start_time = _as_datetime(frame["timestamp"].min())
            end_time = _as_datetime(frame["timestamp"].max())
            return AnalyticsAvailability(
                status="ready",
                manifest=manifest,
                start_time=start_time,
                end_time=end_time,
                title="M3 分析数据可用",
                reason="manifest、处理身份、15 分钟 Parquet 与必需字段已通过只读校验。",
                evidence=(
                    manifest.dataset_id,
                    manifest.preprocess_id,
                    f"15 分钟点数 {len(frame):,}",
                ),
                next_step="选择日期范围查看确定性历史分析。",
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
                next_step="复核日期范围；若仍失败，在数据中心重新生成 M2 产物。",
            ) from exc

    def _validated_artifact(self) -> tuple[DatasetManifest, Path]:
        state = DataService(self._context).inspect_builtin_state()
        if state.error:
            raise AnalyticsError(
                code="ANALYTICS_MANIFEST_IDENTITY_MISMATCH",
                title="数据身份不一致",
                reason="当前原始数据身份与 manifest 不一致，不能继续分析。",
                evidence=tuple(item for item in (state.dataset_id,) if item),
                next_step="在数据中心重新校验数据并生成与当前身份一致的 M2 产物。",
            )
        if state.manifest is None:
            raise AnalyticsError(
                code="ANALYTICS_MANIFEST_MISSING",
                title="M2 manifest 不可用",
                reason="当前没有可验证的处理身份和字段契约。",
                evidence=tuple(item for item in (state.dataset_id,) if item),
                next_step="前往数据中心生成 M2 处理产物。",
            )
        manifest = state.manifest
        if manifest.schema_version != "1.0" or manifest.cadence.get("processed") != "15min":
            raise AnalyticsError(
                code="ANALYTICS_MANIFEST_INCOMPATIBLE",
                title="M2 manifest 版本不兼容",
                reason="M3 仅接受 schema 1.0 的 15 分钟处理产物。",
                evidence=(manifest.schema_version, str(manifest.cadence.get("processed"))),
                next_step="使用当前代码和默认配置重新生成 M2 处理产物。",
            )
        missing_contract = tuple(
            column for column in REQUIRED_COLUMNS if column not in manifest.columns
        )
        if missing_contract:
            raise AnalyticsError(
                code="ANALYTICS_MANIFEST_COLUMNS_MISSING",
                title="M2 字段契约不完整",
                reason="manifest 缺少 M3 确定性分析所需字段。",
                evidence=missing_contract,
                next_step="重新生成 M2 manifest；不要在页面中猜测或补造字段。",
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
                reason="manifest 指向的处理产物与 preprocess_id 目录不一致。",
                evidence=(manifest.preprocess_id,),
                next_step="在数据中心重新生成 M2 处理产物。",
            )
        if not processed_path.is_file():
            raise AnalyticsError(
                code="ANALYTICS_PARQUET_MISSING",
                title="15 分钟处理数据缺失",
                reason="manifest 存在，但对应 Parquet 文件不可用。",
                evidence=(manifest.preprocess_id,),
                next_step="在数据中心重新生成 M2 处理产物。",
            )
        try:
            parquet = pq.ParquetFile(processed_path)  # type: ignore[no-untyped-call]
        except (OSError, ValueError) as exc:
            raise AnalyticsError(
                code="ANALYTICS_PARQUET_UNREADABLE",
                title="15 分钟处理数据不可读",
                reason="Parquet 文件存在，但无法解析其 schema。",
                evidence=(type(exc).__name__, manifest.preprocess_id),
                next_step="重新生成 M2 处理产物并复核磁盘状态。",
            ) from exc
        missing_parquet = tuple(
            column for column in REQUIRED_COLUMNS if column not in parquet.schema_arrow.names
        )
        if missing_parquet:
            raise AnalyticsError(
                code="ANALYTICS_PARQUET_COLUMNS_MISSING",
                title="15 分钟处理数据字段不兼容",
                reason="Parquet 缺少 M3 确定性分析所需字段。",
                evidence=missing_parquet,
                next_step="使用当前 M2 规则重新生成处理产物。",
            )
        split_counts = manifest.splits.get("counts")
        if not isinstance(split_counts, dict):
            raise AnalyticsError(
                code="ANALYTICS_MANIFEST_SPLITS_INVALID",
                title="M2 固定切分契约不完整",
                reason="manifest 没有可验证的 train、validation、test 计数。",
                evidence=(manifest.preprocess_id,),
                next_step="使用当前代码和默认配置重新生成 M2 处理产物。",
            )
        expected_rows = 0
        for value in split_counts.values():
            if not isinstance(value, int):
                raise AnalyticsError(
                    code="ANALYTICS_MANIFEST_SPLITS_INVALID",
                    title="M2 固定切分契约不完整",
                    reason="manifest 的固定切分计数不是整数。",
                    evidence=(manifest.preprocess_id,),
                    next_step="使用当前代码和默认配置重新生成 M2 处理产物。",
                )
            expected_rows += value
        if parquet.metadata.num_rows != expected_rows:
            raise AnalyticsError(
                code="ANALYTICS_PARQUET_ROW_COUNT_MISMATCH",
                title="15 分钟处理数据身份不一致",
                reason="Parquet 行数与 manifest 固定切分计数不一致。",
                evidence=(f"manifest={expected_rows}", f"parquet={parquet.metadata.num_rows}"),
                next_step="重新生成 M2 处理产物；不要继续使用不一致数据。",
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
