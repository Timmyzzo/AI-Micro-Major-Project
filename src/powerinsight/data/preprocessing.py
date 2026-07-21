"""Configuration-driven missing handling, features, aggregation, and time splits."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

import numpy as np
import pandas as pd  # type: ignore[import-untyped]

from powerinsight.config import DataSettings
from powerinsight.data.validation import MEASUREMENT_COLUMNS, ValidationResult, find_missing_blocks
from powerinsight.schemas import DataIssue, DataQualityReport, PreprocessConfig

MEAN_COLUMNS: tuple[str, ...] = (
    "global_active_power_kw",
    "global_reactive_power_kw",
    "voltage_v",
    "global_intensity_a",
)
SUM_COLUMNS: tuple[str, ...] = (
    "sub_metering_1_wh",
    "sub_metering_2_wh",
    "sub_metering_3_wh",
    "global_active_energy_wh",
    "unmetered_energy_wh",
)


@dataclass(frozen=True)
class PreprocessResult:
    """In-memory result before repeatable artifacts are written."""

    preprocess_id: str
    config_hash: str
    minute_frame: pd.DataFrame
    aggregated_frame: pd.DataFrame
    quality_report: DataQualityReport
    imputed_row_count: int
    long_gap_row_count: int
    negative_unmetered_count: int


def config_from_settings(settings: DataSettings) -> PreprocessConfig:
    """Create the immutable processing contract from validated application settings."""
    return PreprocessConfig(
        raw_cadence=settings.raw_cadence,
        target_cadence=settings.target_cadence,
        short_gap_max_minutes=settings.short_gap_max_minutes,
        bucket_min_valid_ratio=settings.bucket_min_valid_ratio,
        unmetered_negative_tolerance_wh=settings.unmetered_negative_tolerance_wh,
        train_end=settings.train_end,
        validation_end=settings.validation_end,
        test_end=settings.test_end,
    )


def preprocess_dataset(
    validation: ValidationResult,
    config: PreprocessConfig,
) -> PreprocessResult:
    """Apply deterministic M2 processing without modifying the validated input frame."""
    config_hash = config_fingerprint(config)
    preprocess_id = build_preprocess_id(validation.dataset.dataset_id, config_hash)
    minute_frame = apply_missing_policy(validation.frame, config)
    minute_frame, negative_count = add_derived_fields(minute_frame, config)
    aggregated = aggregate_minutes(minute_frame, config)
    aggregated = assign_fixed_splits(aggregated, config)
    quality_report = _quality_with_preprocess_issues(validation.report, negative_count)
    return PreprocessResult(
        preprocess_id=preprocess_id,
        config_hash=config_hash,
        minute_frame=minute_frame,
        aggregated_frame=aggregated,
        quality_report=quality_report,
        imputed_row_count=int(minute_frame["imputed_mask"].sum()),
        long_gap_row_count=int(minute_frame["long_gap_mask"].sum()),
        negative_unmetered_count=negative_count,
    )


def apply_missing_policy(frame: pd.DataFrame, config: PreprocessConfig) -> pd.DataFrame:
    """Interpolate only short blocks and retain explicit row-level quality masks."""
    result = frame.copy(deep=True)
    result = result.sort_values("timestamp", kind="stable").reset_index(drop=True)
    missing_mask = result.loc[:, MEASUREMENT_COLUMNS].isna().any(axis=1)
    result["missing_mask"] = missing_mask
    result["imputed_mask"] = False
    result["long_gap_mask"] = False
    blocks = find_missing_blocks(
        result,
        missing_mask=missing_mask,
        cadence=pd.Timedelta(config.raw_cadence),
    )
    indexed_measurements = result.set_index("timestamp").loc[:, MEASUREMENT_COLUMNS]
    interpolation = indexed_measurements.interpolate(method="time", limit_area="inside")
    for block in blocks:
        block_mask = result["timestamp"].between(block.start_time, block.end_time)
        if block.length_minutes <= config.short_gap_max_minutes:
            before_missing = result.loc[block_mask, MEASUREMENT_COLUMNS].isna()
            result.loc[block_mask, MEASUREMENT_COLUMNS] = interpolation.loc[
                block.start_time : block.end_time, MEASUREMENT_COLUMNS
            ].to_numpy()
            after_valid = result.loc[block_mask, MEASUREMENT_COLUMNS].notna()
            result.loc[block_mask, "imputed_mask"] = (before_missing & after_valid).any(axis=1)
        else:
            result.loc[block_mask, "long_gap_mask"] = True
    return result


def add_derived_fields(
    frame: pd.DataFrame,
    config: PreprocessConfig,
) -> tuple[pd.DataFrame, int]:
    """Add energy and calendar fields while retaining significant negative residuals."""
    result = frame.copy(deep=True)
    result["global_active_energy_wh"] = result["global_active_power_kw"] * 1000.0 / 60.0
    raw_unmetered = (
        result["global_active_energy_wh"]
        - result["sub_metering_1_wh"]
        - result["sub_metering_2_wh"]
        - result["sub_metering_3_wh"]
    )
    result["unmetered_energy_raw_wh"] = raw_unmetered
    tiny_negative = raw_unmetered.between(
        -config.unmetered_negative_tolerance_wh,
        0.0,
        inclusive="left",
    )
    result["unmetered_energy_wh"] = raw_unmetered.mask(tiny_negative, 0.0)
    significant_negative = raw_unmetered < -config.unmetered_negative_tolerance_wh
    result["unmetered_negative_mask"] = significant_negative.fillna(False)
    timestamp = result["timestamp"]
    result["hour"] = timestamp.dt.hour.astype("int8")
    result["weekday"] = timestamp.dt.weekday.astype("int8")
    result["is_weekend"] = timestamp.dt.weekday.ge(5)
    result["month"] = timestamp.dt.month.astype("int8")
    return result, int(significant_negative.sum())


def aggregate_minutes(frame: pd.DataFrame, config: PreprocessConfig) -> pd.DataFrame:
    """Aggregate minute measurements with per-field valid-ratio enforcement."""
    raw_delta = pd.Timedelta(config.raw_cadence)
    target_delta = pd.Timedelta(config.target_cadence)
    ratio = target_delta / raw_delta
    if not float(ratio).is_integer() or ratio < 1:
        raise ValueError("target cadence must be an integer multiple of raw cadence")
    expected_minutes = int(ratio)
    indexed = frame.sort_values("timestamp", kind="stable").set_index("timestamp")
    aggregate_parts: dict[str, pd.Series] = {}
    for column in MEAN_COLUMNS:
        values = indexed[column].resample(config.target_cadence).mean()
        valid_ratio = indexed[column].resample(config.target_cadence).count() / expected_minutes
        aggregate_parts[column] = values.where(valid_ratio >= config.bucket_min_valid_ratio)
    for column in SUM_COLUMNS:
        values = indexed[column].resample(config.target_cadence).sum(min_count=1)
        valid_ratio = indexed[column].resample(config.target_cadence).count() / expected_minutes
        aggregate_parts[column] = values.where(valid_ratio >= config.bucket_min_valid_ratio)
    aggregated = pd.DataFrame(aggregate_parts)
    aggregated["missing_ratio"] = (
        indexed["missing_mask"].astype(int).resample(config.target_cadence).sum() / expected_minutes
    )
    aggregated["imputed_ratio"] = (
        indexed["imputed_mask"].astype(int).resample(config.target_cadence).sum() / expected_minutes
    )
    aggregated["long_gap"] = indexed["long_gap_mask"].resample(config.target_cadence).max()
    aggregated = aggregated.reset_index()
    timestamp = aggregated["timestamp"]
    aggregated["hour"] = timestamp.dt.hour.astype("int8")
    aggregated["weekday"] = timestamp.dt.weekday.astype("int8")
    aggregated["is_weekend"] = timestamp.dt.weekday.ge(5)
    aggregated["month"] = timestamp.dt.month.astype("int8")
    aggregated["quality_flag"] = np.select(
        (
            aggregated["long_gap"].astype(bool),
            aggregated["global_active_power_kw"].isna(),
            aggregated["imputed_ratio"].gt(0),
        ),
        ("long_gap", "low_valid_ratio", "imputed"),
        default="ok",
    )
    return aggregated


def assign_fixed_splits(frame: pd.DataFrame, config: PreprocessConfig) -> pd.DataFrame:
    """Assign every processed row to the fixed train, validation, or test month range."""
    result = frame.copy(deep=True)
    timestamps = result["timestamp"]
    split = np.select(
        (
            timestamps <= config.train_end,
            timestamps <= config.validation_end,
            timestamps <= config.test_end,
        ),
        ("train", "validation", "test"),
        default="outside",
    )
    result["split"] = split
    outside_count = int(result["split"].eq("outside").sum())
    if outside_count:
        raise ValueError(f"{outside_count} processed rows fall outside configured split boundaries")
    return result


def config_fingerprint(config: PreprocessConfig) -> str:
    """Return a stable SHA-256 over the complete processing configuration."""
    payload = json.dumps(
        config.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest().upper()


def build_preprocess_id(dataset_id: str, config_hash: str) -> str:
    """Build a stable preprocessing ID from the dataset and configuration identities."""
    dataset_suffix = dataset_id.removeprefix("ds_")[-8:]
    return f"prep_{dataset_suffix}_{config_hash[:12].lower()}"


def _quality_with_preprocess_issues(
    report: DataQualityReport,
    negative_unmetered_count: int,
) -> DataQualityReport:
    if not negative_unmetered_count:
        return report
    issue = DataIssue(
        code="PREP_NEGATIVE_UNMETERED_ENERGY",
        severity="warning",
        message="发现明显为负的未分项电量，已保留原值而未静默截断。",
        count=negative_unmetered_count,
        suggested_action="在分析页面标记这些记录，并结合分项测量精度解释。",
    )
    return report.model_copy(update={"status": "attention", "issues": (*report.issues, issue)})
