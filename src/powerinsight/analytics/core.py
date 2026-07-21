"""Pure, deterministic M3 calculations over processed 15-minute data."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import cast

import numpy as np
import pandas as pd  # type: ignore[import-untyped]

from powerinsight.schemas import (
    AnalyticsKpis,
    AnalyticsRangeSummary,
    AnalyticsStatus,
    SubmeterBreakdown,
    SubmeterComponent,
)

CADENCE = pd.Timedelta(minutes=15)
WEEKDAY_LABELS = ("星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日")
ENERGY_COLUMNS = (
    ("sub_metering_1", "厨房", "sub_metering_1_wh"),
    ("sub_metering_2", "洗衣房", "sub_metering_2_wh"),
    ("sub_metering_3", "热水器 / 空调", "sub_metering_3_wh"),
    ("unmetered", "未分项", "unmetered_energy_wh"),
)


@dataclass(frozen=True)
class AnalyticsResult:
    """Complete deterministic result consumed by the service and Streamlit page."""

    status: AnalyticsStatus
    range_summary: AnalyticsRangeSummary
    kpis: AnalyticsKpis
    trend: pd.DataFrame
    hourly_profile: pd.DataFrame
    weekday_profile: pd.DataFrame
    day_type_profile: pd.DataFrame
    submeter: SubmeterBreakdown
    evidence: tuple[str, ...]
    has_long_gap: bool


def analyze_frame(
    frame: pd.DataFrame,
    *,
    preprocess_id: str,
    start: datetime,
    end_exclusive: datetime,
    max_chart_points: int,
    source_negative_unmetered_records: int = 0,
) -> AnalyticsResult:
    """Analyze one half-open local-naive interval without modifying the input frame."""
    if start >= end_exclusive:
        raise ValueError("analysis start must be earlier than end")
    if max_chart_points < 2:
        raise ValueError("max_chart_points must be at least 2")

    selected = frame.loc[frame["timestamp"].ge(start) & frame["timestamp"].lt(end_exclusive)].copy(
        deep=True
    )
    selected = selected.sort_values("timestamp", kind="stable").reset_index(drop=True)
    expected_points = int((pd.Timestamp(end_exclusive) - pd.Timestamp(start)) / CADENCE)
    actual_points = len(selected)
    valid_load_points = int(selected["global_active_power_kw"].notna().sum())
    missing_points = max(expected_points - valid_load_points, 0)
    coverage_ratio = valid_load_points / expected_points if expected_points else 0.0
    actual_start = _to_datetime(selected["timestamp"].min()) if actual_points else None
    actual_end = _to_datetime(selected["timestamp"].max()) if actual_points else None
    range_summary = AnalyticsRangeSummary(
        preprocess_id=preprocess_id,
        requested_start=start,
        requested_end_exclusive=end_exclusive,
        actual_start=actual_start,
        actual_end=actual_end,
        expected_points=expected_points,
        actual_points=actual_points,
        valid_load_points=valid_load_points,
        missing_points=missing_points,
        coverage_ratio=coverage_ratio,
    )

    kpis = _calculate_kpis(selected, coverage_ratio)
    submeter = _calculate_submeter_breakdown(
        selected,
        kpis.total_active_energy_kwh,
        source_negative_unmetered_records=source_negative_unmetered_records,
    )
    has_long_gap = bool(selected["long_gap"].fillna(False).any()) if actual_points else False
    if valid_load_points == 0:
        status: AnalyticsStatus = "empty"
    elif coverage_ratio < 1.0 or has_long_gap or submeter.negative_unmetered_records:
        status = "attention"
    else:
        status = "ready"

    trend = downsample_trend(
        selected.loc[:, ["timestamp", "global_active_power_kw", "long_gap"]],
        max_points=max_chart_points,
    )
    hourly = _profile(selected, [selected["timestamp"].dt.hour], ["hour"])
    weekday = _weekday_profile(selected)
    day_type = _day_type_profile(selected)
    evidence = _build_evidence(range_summary, kpis, submeter, has_long_gap)
    return AnalyticsResult(
        status=status,
        range_summary=range_summary,
        kpis=kpis,
        trend=trend,
        hourly_profile=hourly,
        weekday_profile=weekday,
        day_type_profile=day_type,
        submeter=submeter,
        evidence=evidence,
        has_long_gap=has_long_gap,
    )


def downsample_trend(frame: pd.DataFrame, *, max_points: int) -> pd.DataFrame:
    """Deterministically limit points while retaining missing-run boundaries."""
    ordered = frame.sort_values("timestamp", kind="stable").reset_index(drop=True).copy(deep=True)
    if len(ordered) <= max_points:
        return ordered

    valid = ordered["global_active_power_kw"].notna().to_numpy()
    transitions = np.flatnonzero(valid[1:] != valid[:-1]) + 1
    mandatory: set[int] = {0, len(ordered) - 1}
    for index in transitions:
        integer_index = int(index)
        mandatory.update((max(integer_index - 1, 0), integer_index))
    mandatory_indices = sorted(mandatory)
    if len(mandatory_indices) >= max_points:
        chosen = _even_positions(np.asarray(mandatory_indices), max_points)
    else:
        remaining = np.setdiff1d(np.arange(len(ordered)), np.asarray(mandatory_indices))
        filler = _even_positions(remaining, max_points - len(mandatory_indices))
        chosen = np.sort(np.concatenate((np.asarray(mandatory_indices), filler)))
    return ordered.iloc[chosen].reset_index(drop=True)


def _calculate_kpis(frame: pd.DataFrame, coverage_ratio: float) -> AnalyticsKpis:
    valid_power = frame.dropna(subset=["global_active_power_kw"])
    if valid_power.empty:
        return AnalyticsKpis(
            total_active_energy_kwh=None,
            average_active_power_kw=None,
            peak_active_power_kw=None,
            peak_time=None,
            minimum_active_power_kw=None,
            minimum_time=None,
            coverage_ratio=coverage_ratio,
        )
    peak_index = valid_power["global_active_power_kw"].idxmax()
    minimum_index = valid_power["global_active_power_kw"].idxmin()
    energy_wh = frame["global_active_energy_wh"].sum(min_count=1)
    return AnalyticsKpis(
        total_active_energy_kwh=float(energy_wh / 1000.0) if pd.notna(energy_wh) else None,
        average_active_power_kw=float(valid_power["global_active_power_kw"].mean()),
        peak_active_power_kw=float(valid_power.loc[peak_index, "global_active_power_kw"]),
        peak_time=_to_datetime(valid_power.loc[peak_index, "timestamp"]),
        minimum_active_power_kw=float(valid_power.loc[minimum_index, "global_active_power_kw"]),
        minimum_time=_to_datetime(valid_power.loc[minimum_index, "timestamp"]),
        coverage_ratio=coverage_ratio,
    )


def _calculate_submeter_breakdown(
    frame: pd.DataFrame,
    total_active_energy_kwh: float | None,
    *,
    source_negative_unmetered_records: int,
) -> SubmeterBreakdown:
    aggregated_negative_count = int(frame["unmetered_energy_wh"].lt(0).fillna(False).sum())
    negative_count = max(aggregated_negative_count, source_negative_unmetered_records)
    totals: list[float | None] = []
    for _, _, column in ENERGY_COLUMNS:
        value = frame[column].sum(min_count=1)
        totals.append(float(value / 1000.0) if pd.notna(value) else None)
    shares_available = bool(
        total_active_energy_kwh is not None
        and total_active_energy_kwh > 0
        and negative_count == 0
        and all(value is not None and value >= 0 for value in totals)
    )
    share_denominator = total_active_energy_kwh if shares_available else None
    components = tuple(
        SubmeterComponent(
            key=key,  # type: ignore[arg-type]
            label=label,
            energy_kwh=value,
            share_ratio=(value / share_denominator)
            if share_denominator is not None and value is not None
            else None,
        )
        for (key, label, _), value in zip(ENERGY_COLUMNS, totals, strict=True)
    )
    if negative_count:
        note = "M2 质量记录中存在负未分项原值；为避免误导，本范围不计算分项占比。"
    elif not shares_available:
        note = "总电量或分项总量无效，本范围不计算分项占比。"
    else:
        note = "分项占比以有效总有功电量为分母；能量统一为 kWh。"
    return SubmeterBreakdown(
        total_active_energy_kwh=total_active_energy_kwh,
        components=components,
        negative_unmetered_records=negative_count,
        shares_available=shares_available,
        note=note,
    )


def _profile(
    frame: pd.DataFrame,
    groupers: list[pd.Series],
    names: list[str],
) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(
            columns=[*names, "average_power_kw", "valid_samples", "total_samples", "coverage_ratio"]
        )
    working = frame.assign(
        **{name: grouper.to_numpy() for name, grouper in zip(names, groupers, strict=True)}
    )
    grouped = working.groupby(names, observed=True, sort=True)
    result = grouped["global_active_power_kw"].agg(average_power_kw="mean", valid_samples="count")
    result["total_samples"] = grouped.size()
    result["coverage_ratio"] = result["valid_samples"] / result["total_samples"]
    return result.reset_index()


def _weekday_profile(frame: pd.DataFrame) -> pd.DataFrame:
    result = _profile(frame, [frame["timestamp"].dt.weekday], ["weekday"])
    if result.empty:
        result["weekday_label"] = pd.Series(dtype="string")
        return result
    result["weekday"] = result["weekday"].astype(int)
    result["weekday_label"] = result["weekday"].map(dict(enumerate(WEEKDAY_LABELS)))
    return result.sort_values("weekday", kind="stable").reset_index(drop=True)


def _day_type_profile(frame: pd.DataFrame) -> pd.DataFrame:
    timestamps = frame["timestamp"]
    result = _profile(
        frame,
        [timestamps.dt.weekday.ge(5), timestamps.dt.hour],
        ["is_weekend", "hour"],
    )
    if result.empty:
        result["day_type"] = pd.Series(dtype="string")
        return result
    result["day_type"] = result["is_weekend"].map({False: "工作日", True: "周末"})
    return result


def _build_evidence(
    summary: AnalyticsRangeSummary,
    kpis: AnalyticsKpis,
    submeter: SubmeterBreakdown,
    has_long_gap: bool,
) -> tuple[str, ...]:
    items = [
        (
            f"当前范围覆盖率 {summary.coverage_ratio:.1%}，"
            f"有效点 {summary.valid_load_points:,}/{summary.expected_points:,}。"
        ),
    ]
    if kpis.peak_time is not None and kpis.peak_active_power_kw is not None:
        items.append(
            f"在当前数据范围内，峰值功率为 {kpis.peak_active_power_kw:.2f} kW，"
            f"发生于 {kpis.peak_time:%Y-%m-%d %H:%M}。"
        )
    if kpis.total_active_energy_kwh is not None:
        items.append(f"基于有效能量字段累计有功电量 {kpis.total_active_energy_kwh:,.1f} kWh。")
    if has_long_gap:
        items.append("所选范围包含 M2 标记的长缺失，趋势保持断开，结论仅基于有效数据。")
    if submeter.negative_unmetered_records:
        items.append(
            f"M2 质量记录包含 {submeter.negative_unmetered_records:,} 条负未分项原值，"
            "原值保留且未生成占比。"
        )
    items.append("这是本地确定性历史分析，没有训练模型，也没有预测未来。")
    return tuple(items)


def _even_positions(values: np.ndarray, count: int) -> np.ndarray:
    if count <= 0 or values.size == 0:
        return np.asarray([], dtype=int)
    if count >= values.size:
        return values.astype(int, copy=False)
    positions = np.linspace(0, values.size - 1, num=count, dtype=int)
    return values[positions].astype(int, copy=False)


def _to_datetime(value: object) -> datetime | None:
    if pd.isna(value):
        return None
    return cast(datetime, pd.Timestamp(value).to_pydatetime())
