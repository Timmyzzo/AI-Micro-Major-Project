"""Repeatable Parquet and JSON manifest artifact creation."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path

import pandas as pd  # type: ignore[import-untyped]

from powerinsight import __version__
from powerinsight.data.preprocessing import PreprocessResult
from powerinsight.data.validation import ValidationResult
from powerinsight.schemas import DatasetManifest, PreprocessConfig, ProcessedDatasetRecord

COLUMN_CONTRACT: dict[str, dict[str, str]] = {
    "row_index": {"dtype": "Int64", "unit": "source row index"},
    "timestamp": {"dtype": "datetime64[ns]", "unit": "dataset-local naive time"},
    "global_active_power_kw": {"dtype": "float64", "unit": "kW"},
    "global_reactive_power_kw": {"dtype": "float64", "unit": "kW"},
    "voltage_v": {"dtype": "float64", "unit": "V"},
    "global_intensity_a": {"dtype": "float64", "unit": "A"},
    "sub_metering_1_wh": {"dtype": "float64", "unit": "Wh"},
    "sub_metering_2_wh": {"dtype": "float64", "unit": "Wh"},
    "sub_metering_3_wh": {"dtype": "float64", "unit": "Wh"},
    "global_active_energy_wh": {"dtype": "float64", "unit": "Wh"},
    "unmetered_energy_raw_wh": {"dtype": "float64", "unit": "Wh"},
    "unmetered_energy_wh": {"dtype": "float64", "unit": "Wh"},
    "missing_mask": {"dtype": "bool", "unit": "flag"},
    "imputed_mask": {"dtype": "bool", "unit": "flag"},
    "long_gap_mask": {"dtype": "bool", "unit": "flag"},
    "unmetered_negative_mask": {"dtype": "bool", "unit": "flag"},
    "missing_ratio": {"dtype": "float64", "unit": "ratio"},
    "imputed_ratio": {"dtype": "float64", "unit": "ratio"},
    "long_gap": {"dtype": "bool", "unit": "flag"},
    "hour": {"dtype": "int8", "unit": "hour of day"},
    "weekday": {"dtype": "int8", "unit": "Monday=0"},
    "is_weekend": {"dtype": "bool", "unit": "flag"},
    "month": {"dtype": "int8", "unit": "month number"},
    "quality_flag": {"dtype": "string", "unit": "category"},
    "split": {"dtype": "string", "unit": "train/validation/test"},
}


def write_preprocess_artifacts(
    validation: ValidationResult,
    result: PreprocessResult,
    config: PreprocessConfig,
    *,
    data_dir: Path,
) -> tuple[ProcessedDatasetRecord, DatasetManifest]:
    """Atomically write stable M2 artifacts and return their non-sensitive metadata."""
    minute_alias = f"data/interim/{result.preprocess_id}/minute.parquet"
    processed_alias = f"data/processed/{result.preprocess_id}/power_15min.parquet"
    manifest_alias = f"data/manifests/{validation.dataset.dataset_id}.json"
    minute_path = data_dir / "interim" / result.preprocess_id / "minute.parquet"
    processed_path = data_dir / "processed" / result.preprocess_id / "power_15min.parquet"
    manifest_path = data_dir / "manifests" / f"{validation.dataset.dataset_id}.json"
    _write_parquet_atomic(result.minute_frame, minute_path)
    _write_parquet_atomic(result.aggregated_frame, processed_path)
    manifest = build_manifest(
        validation,
        result,
        config,
        minute_path_alias=minute_alias,
        processed_path_alias=processed_alias,
        manifest_path_alias=manifest_alias,
    )
    _write_json_atomic(manifest, manifest_path)
    record = ProcessedDatasetRecord(
        schema_version="1.0",
        preprocess_id=result.preprocess_id,
        dataset_id=validation.dataset.dataset_id,
        config_hash=result.config_hash,
        minute_path_alias=minute_alias,
        processed_path_alias=processed_alias,
        manifest_path_alias=manifest_alias,
        minute_rows=len(result.minute_frame),
        processed_rows=len(result.aggregated_frame),
        split_counts=_split_counts(result.aggregated_frame),
        status="completed",
        created_at=manifest.created_at,
    )
    return record, manifest


def build_manifest(
    validation: ValidationResult,
    result: PreprocessResult,
    config: PreprocessConfig,
    *,
    minute_path_alias: str,
    processed_path_alias: str,
    manifest_path_alias: str,
) -> DatasetManifest:
    """Build a serializable provenance object from computed data and configuration."""
    if validation.dataset.start_time is None or validation.dataset.end_time is None:
        raise ValueError("validated dataset is missing its time range")
    longest = max(
        result.quality_report.missing_blocks,
        key=lambda block: block.length_minutes,
        default=None,
    )
    split_counts = _split_counts(result.aggregated_frame)
    return DatasetManifest(
        schema_version="1.0",
        dataset_id=validation.dataset.dataset_id,
        preprocess_id=result.preprocess_id,
        config_hash=result.config_hash,
        source_path_alias=validation.dataset.path_alias,
        source_sha256=validation.dataset.sha256,
        source_rows=validation.dataset.row_count,
        start_time=validation.dataset.start_time,
        end_time=validation.dataset.end_time,
        cadence={
            "raw": config.raw_cadence,
            "processed": config.target_cadence,
        },
        columns=COLUMN_CONTRACT,
        missing_summary={
            "measurement_missing_rows": result.quality_report.measurement_missing_row_count,
            "missing_blocks": len(result.quality_report.missing_blocks),
            "longest_block_minutes": longest.length_minutes if longest else 0,
            "blocks": [
                block.model_dump(mode="json") for block in result.quality_report.missing_blocks
            ],
        },
        preprocessing={
            **config.model_dump(mode="json"),
            "imputed_rows": result.imputed_row_count,
            "long_gap_rows": result.long_gap_row_count,
            "negative_unmetered_rows": result.negative_unmetered_count,
        },
        splits={
            "boundaries": {
                "train_end": config.train_end.isoformat(),
                "validation_end": config.validation_end.isoformat(),
                "test_end": config.test_end.isoformat(),
            },
            "counts": split_counts,
        },
        artifacts={
            "minute": minute_path_alias,
            "processed": processed_path_alias,
            "manifest": manifest_path_alias,
        },
        quality_report=result.quality_report,
        created_at=datetime.now(UTC),
        software_versions={
            "powerinsight": __version__,
            "pandas": metadata.version("pandas"),
            "numpy": metadata.version("numpy"),
            "pyarrow": metadata.version("pyarrow"),
        },
    )


def _split_counts(frame: pd.DataFrame) -> dict[str, int]:
    counts = frame["split"].value_counts()
    return {name: int(counts.get(name, 0)) for name in ("train", "validation", "test")}


def _write_parquet_atomic(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    try:
        frame.to_parquet(temporary, index=False)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _write_json_atomic(manifest: DatasetManifest, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    payload = json.dumps(
        manifest.model_dump(mode="json"),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    try:
        temporary.write_text(f"{payload}\n", encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
