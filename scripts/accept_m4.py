"""Run real-data M4 model, interval, cache, and compatibility acceptance."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

from powerinsight.forecasting.registry import write_json
from powerinsight.paths import display_path
from powerinsight.services.forecast_service import ForecastService
from powerinsight.services.runtime import initialize_runtime


def main() -> None:
    """Load every frozen candidate at one common test origin and print real facts."""
    context = initialize_runtime()
    schema_before = _sqlite_schema_hash(context.paths.database_path)
    service = ForecastService(context)
    availability = service.inspect_availability()
    if availability.status != "ready" or not availability.models or not availability.origins:
        raise RuntimeError(f"M4 acceptance blocked: {availability.title}: {availability.reason}")
    defaults = [model for model in availability.models if model.is_default]
    if len(defaults) != 1:
        raise RuntimeError(
            f"M4 registry must contain exactly one default model, found {len(defaults)}"
        )
    forecast_start = availability.origins[0]
    model_results: list[dict[str, object]] = []
    default_result = None
    for model in availability.models:
        result = service.predict(
            model_id=model.model_id,
            forecast_start=forecast_start,
            requested_device="auto",
            allow_cache=False,
        )
        if len(result.context) != 672 or len(result.forecast) != 96:
            raise RuntimeError(f"forecast shape changed for {model.model_id}")
        test = result.metrics.get("test")
        interval = result.metrics.get("interval")
        if not isinstance(test, dict) or not isinstance(interval, dict):
            raise RuntimeError(f"metrics contract changed for {model.model_id}")
        model_results.append(
            {
                "model_id": model.model_id,
                "display_name": model.display_name,
                "run_id": model.run_id,
                "device": result.device,
                "latency_ms": result.latency_ms,
                "training_seconds": model.training_seconds,
                "peak_gpu_memory_bytes": model.peak_gpu_memory_bytes,
                "validation_mae": model.validation_mae,
                "test": test,
                "interval": {
                    "coverage": interval.get("coverage"),
                    "average_width_kw": interval.get("average_width_kw"),
                },
                "is_default": model.is_default,
                "config_fingerprint": model.config_fingerprint,
            }
        )
        if model.is_default:
            default_result = result
    assert default_result is not None
    cached = service.predict(
        model_id=default_result.model.model_id,
        forecast_start=forecast_start,
        requested_device="auto",
        allow_cache=True,
    )
    if cached.status != "cached" or cached.forecast_id != default_result.forecast_id:
        raise RuntimeError("offline default forecast cache was not reused")

    patchtst = next(model for model in availability.models if model.model_type == "patchtst")
    patchtst_cpu = service.predict(
        model_id=patchtst.model_id,
        forecast_start=forecast_start,
        requested_device="cpu",
        allow_cache=False,
    )
    export = default_result.export_frame()
    required_export_columns = {
        "timestamp",
        "y_pred_kw",
        "lower_kw",
        "upper_kw",
        "y_true_kw",
        "is_outside_interval",
        "forecast_id",
        "model_id",
        "run_id",
        "dataset_id",
        "preprocess_id",
        "config_fingerprint",
        "interval_level",
        "generated_at",
        "result_status",
        "device",
    }
    if set(export.columns) != required_export_columns or len(export) != 96:
        raise RuntimeError("forecast CSV export contract changed")

    demo_manifest = {
        "schema_version": "1.0",
        "forecast_id": default_result.forecast_id,
        "model_id": default_result.model.model_id,
        "dataset_id": default_result.model.dataset_id,
        "preprocess_id": default_result.model.preprocess_id,
        "forecast_start": forecast_start,
        "cache_path_alias": default_result.cache_path_alias,
        "created_at": default_result.created_at,
    }
    demo_path = context.paths.artifact_dir / "demo" / "demo_manifest.json"
    write_json(demo_path, demo_manifest)
    schema_after = _sqlite_schema_hash(context.paths.database_path)
    if schema_before != schema_after:
        raise RuntimeError("M4 unexpectedly changed SQLite schema")

    summary_path = next((context.paths.root / "models" / "registry").glob("m4_*.json"))
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    payload = {
        "dataset_id": default_result.model.dataset_id,
        "preprocess_id": default_result.model.preprocess_id,
        "experiment_id": summary.get("experiment_id"),
        "code_commit": summary.get("code_commit"),
        "forecast_start": forecast_start.isoformat(),
        "window_counts": summary.get("window_counts"),
        "model_count": len(model_results),
        "default_model_id": default_result.model.model_id,
        "default_reason": default_result.model.default_reason,
        "patchtst_best_naive_mae_improvement": summary.get("patchtst_best_naive_mae_improvement"),
        "patchtst_meets_five_percent_gate": summary.get("patchtst_meets_five_percent_gate"),
        "models": model_results,
        "patchtst_cpu_latency_ms": patchtst_cpu.latency_ms,
        "cache_status": cached.status,
        "cache_path_alias": cached.cache_path_alias,
        "demo_manifest_path_alias": display_path(demo_path, root=context.paths.root),
        "export_rows": len(export),
        "export_columns": list(export.columns),
        "sqlite_schema_sha256": schema_after,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _sqlite_schema_hash(path: Path) -> str:
    with sqlite3.connect(path) as connection:
        rows = connection.execute(
            "SELECT sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY type, name"
        ).fetchall()
    schema = "\n".join(str(row[0] or "") for row in rows)
    return hashlib.sha256(schema.encode("utf-8")).hexdigest().upper()


if __name__ == "__main__":
    main()
