"""Small complete M4 registry fixture for services and AppTest."""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pandas as pd

from powerinsight.data.catalog import build_dataset_id, compute_sha256
from powerinsight.forecasting import TargetScaler
from powerinsight.forecasting.registry import (
    RegisteredModel,
    config_fingerprint,
    file_sha256,
    registry_paths,
    write_json,
)
from powerinsight.paths import display_path
from powerinsight.persistence.metadata import register_dataset
from powerinsight.schemas import DataQualityReport, DatasetManifest, DatasetRecord
from powerinsight.services.runtime import RuntimeContext


def prepare_forecast_fixture(context: RuntimeContext) -> RegisteredModel:
    """Write a compatible seasonal-day model and two valid June test origins."""
    context.paths.builtin_csv.parent.mkdir(parents=True, exist_ok=True)
    context.paths.builtin_csv.write_text("fixture\n", encoding="utf-8")
    source_alias = display_path(context.paths.builtin_csv, root=context.paths.root)
    source_hash = compute_sha256(context.paths.builtin_csv)
    dataset_id = build_dataset_id(source_alias, source_hash)
    preprocess_id = "prep_fixture_m4"
    config_hash = "A" * 64
    processed_dir = context.paths.data_dir / "processed" / preprocess_id
    processed_dir.mkdir(parents=True, exist_ok=True)
    train_periods = 1000
    test_periods = 900
    train_timestamps = pd.date_range("2007-01-01", periods=train_periods, freq="15min")
    test_timestamps = pd.date_range("2007-06-01", periods=test_periods, freq="15min")
    train_values = (1.5 + np.sin(np.arange(train_periods) * 2 * np.pi / 96)).astype(np.float64)
    test_values = (1.5 + np.sin(np.arange(test_periods) * 2 * np.pi / 96)).astype(np.float64)
    train_frame = pd.DataFrame(
        {
            "timestamp": train_timestamps,
            "global_active_power_kw": train_values,
            "long_gap": False,
            "split": "train",
        }
    )
    test_frame = pd.DataFrame(
        {
            "timestamp": test_timestamps,
            "global_active_power_kw": test_values,
            "long_gap": False,
            "split": "test",
        }
    )
    frame = pd.concat((train_frame, test_frame), ignore_index=True)
    periods = len(frame)
    timestamps = frame["timestamp"]
    values = frame["global_active_power_kw"].to_numpy()
    frame.to_parquet(processed_dir / "power_15min.parquet", index=False)
    report = DataQualityReport(
        dataset_id=dataset_id,
        validation_version="1.0",
        status="usable",
        score=100.0,
        row_count=periods,
        parsed_timestamp_count=periods,
        duplicate_count=0,
        cadence_violations=0,
        missing_cells_by_column={},
        measurement_missing_row_count=0,
        missing_blocks=(),
        issues=(),
        generated_at=datetime.now(UTC),
    )
    register_dataset(
        context.paths.database_path,
        DatasetRecord(
            schema_version="1.0",
            dataset_id=dataset_id,
            name="fixture",
            source_type="built_in",
            path_alias=source_alias,
            sha256=source_hash,
            size_bytes=context.paths.builtin_csv.stat().st_size,
            row_count=periods,
            field_count=4,
            start_time=pd.Timestamp(timestamps.iloc[0]).to_pydatetime(),
            end_time=pd.Timestamp(timestamps.iloc[-1]).to_pydatetime(),
            cadence="15min",
            status="validated",
            created_at=datetime.now(UTC),
        ),
        report,
    )
    manifest = DatasetManifest(
        schema_version="1.0",
        dataset_id=dataset_id,
        preprocess_id=preprocess_id,
        config_hash=config_hash,
        source_path_alias=source_alias,
        source_sha256=source_hash,
        source_rows=periods,
        source_fields=4,
        start_time=pd.Timestamp(timestamps.iloc[0]).to_pydatetime(),
        end_time=pd.Timestamp(timestamps.iloc[-1]).to_pydatetime(),
        cadence={"raw": "15min", "processed": "15min"},
        columns={},
        missing_summary={},
        preprocessing={},
        splits={"counts": {"train": train_periods, "validation": 0, "test": test_periods}},
        artifacts={"processed": f"data/processed/{preprocess_id}/power_15min.parquet"},
        quality_report=report,
        created_at=datetime.now(UTC),
        software_versions={},
    )
    manifest_path = context.paths.data_dir / "manifests" / f"{dataset_id}.json"
    write_json(manifest_path, manifest.model_dump(mode="json"))

    scaler = TargetScaler.fit(values, split="train")
    scaler_path = context.paths.root / "models" / "scalers" / "fixture" / "target_scaler.json"
    write_json(scaler_path, scaler.to_dict())
    model_id = "mdl_seasonal_day_fixture"
    paths = registry_paths(context.paths.root, model_id)
    metrics = {
        "schema_version": "1.0",
        "model_id": model_id,
        "test": {"mae": 0.1, "rmse": 0.2, "wape": 0.05, "smape": 0.04, "r2": 0.9},
        "interval": {"coverage": 0.9, "average_width_kw": 0.5},
        "horizons": {
            label: {"mae": 0.1, "rmse": 0.2, "wape": 0.05} for label in ("1h", "6h", "12h", "24h")
        },
        "steps": [
            {"step": index + 1, "minutes": (index + 1) * 15, "mae": 0.1, "rmse": 0.2}
            for index in range(96)
        ],
    }
    write_json(paths["metrics"], metrics)
    write_json(
        paths["conformal"],
        {"schema_version": "1.0", "interval_level": 0.9, "quantiles_kw": [0.25] * 96},
    )
    paths["card"].parent.mkdir(parents=True, exist_ok=True)
    paths["card"].write_text("# fixture model card\n", encoding="utf-8")
    snapshot = {
        "window": {"context_length": 672, "prediction_length": 96},
        "model": {"context_length": 672, "prediction_length": 96},
        "training": {"trainable": False},
        "data_config_hash": config_hash,
    }
    record = RegisteredModel(
        model_id=model_id,
        run_id="run_fixture",
        model_type="seasonal_day",
        display_name="前一日同刻",
        dataset_id=dataset_id,
        preprocess_id=preprocess_id,
        data_config_hash=config_hash,
        config_fingerprint=config_fingerprint(snapshot),
        context_length=672,
        prediction_length=96,
        interval_level=0.9,
        model_config_snapshot=snapshot["model"],  # type: ignore[arg-type]
        training_config_snapshot=snapshot["training"],  # type: ignore[arg-type]
        checkpoint_path_alias=None,
        checkpoint_sha256=None,
        scaler_path_alias=display_path(scaler_path, root=context.paths.root),
        scaler_sha256=file_sha256(scaler_path),
        conformal_path_alias=display_path(paths["conformal"], root=context.paths.root),
        metrics_path_alias=display_path(paths["metrics"], root=context.paths.root),
        model_card_path_alias=display_path(paths["card"], root=context.paths.root),
        validation_mae=0.1,
        test_mae=0.1,
        test_rmse=0.2,
        is_default=True,
        default_reason="测试夹具默认。",
        code_commit="fixture",
        device="cpu",
        training_seconds=0.0,
        peak_gpu_memory_bytes=None,
        created_at=datetime.now(UTC),
        known_limitations=("合成测试夹具，不是正式结果。",),
    )
    write_json(paths["model"], record.model_dump(mode="json"))
    return record
