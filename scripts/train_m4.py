"""Train, evaluate, calibrate, and register the complete M4 model comparison."""

from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd  # type: ignore[import-untyped]
import torch
import yaml

from powerinsight.forecasting import (
    TargetScaler,
    WindowConfig,
    build_windows,
    calibrate_conformal,
    compute_forecast_metrics,
    compute_horizon_metrics,
    compute_step_metrics,
    interval_metrics,
    naive_predict,
)
from powerinsight.forecasting.models import (
    LSTMForecaster,
    TorchTrainingConfig,
    TrainingResult,
    build_patchtst,
    load_model,
    predict_torch,
    save_model,
    select_and_fit_ridge,
    train_torch_model,
)
from powerinsight.forecasting.registry import (
    RegisteredModel,
    artifact_alias,
    config_fingerprint,
    file_sha256,
    registry_paths,
    utc_now,
    write_json,
)
from powerinsight.persistence.metadata import register_model_run
from powerinsight.services.data_service import DataService
from powerinsight.services.runtime import initialize_runtime

DISPLAY_NAMES = {
    "last_value": "前一时刻",
    "seasonal_day": "前一日同刻",
    "seasonal_week": "前一周同刻",
    "ridge": "Ridge",
    "lstm": "小型 LSTM",
    "patchtst": "小型单变量 PatchTST",
}


@dataclass
class Candidate:
    model_type: str
    model: object | None
    model_config: dict[str, object]
    training_config: dict[str, object]
    validation_prediction: np.ndarray
    test_prediction: np.ndarray
    validation_mae: float
    best_epoch: int | None
    training_seconds: float
    peak_gpu_memory_bytes: int | None
    history: list[dict[str, object]]
    selection: dict[str, object]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("configs/default.yaml"))
    parser.add_argument(
        "--model-config", type=Path, default=Path("configs/model/patchtst_small.yaml")
    )
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    parser.add_argument("--train-stride", type=int, default=4)
    parser.add_argument("--eval-stride", type=int, default=96)
    parser.add_argument("--max-epochs", type=int)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    context = initialize_runtime(config_path=args.config)
    data_state = DataService(context).inspect_builtin_state()
    if data_state.manifest is None or not data_state.processed_exists:
        raise SystemExit("M2 processed data and manifest are required before M4 training")
    manifest = data_state.manifest
    processed_path = (
        context.paths.data_dir / "processed" / manifest.preprocess_id / "power_15min.parquet"
    )
    frame = pd.read_parquet(
        processed_path,
        columns=["timestamp", "global_active_power_kw", "long_gap", "split"],
    )
    context_length = context.settings.forecast.context_length
    prediction_length = context.settings.forecast.prediction_length
    train_windows = build_windows(
        frame,
        split="train",
        config=WindowConfig(context_length, prediction_length, stride=args.train_stride),
    )
    validation_windows = build_windows(
        frame,
        split="validation",
        config=WindowConfig(context_length, prediction_length, stride=args.eval_stride),
    )
    test_windows = build_windows(
        frame,
        split="test",
        config=WindowConfig(context_length, prediction_length, stride=args.eval_stride),
    )
    if (
        min(len(train_windows.context), len(validation_windows.context), len(test_windows.context))
        < 2
    ):
        raise SystemExit("formal M4 windows are insufficient after leakage and missing-data checks")

    train_points = frame.loc[
        frame["split"].eq("train") & frame["global_active_power_kw"].notna(),
        "global_active_power_kw",
    ].to_numpy(dtype=np.float32)
    target_scaler = TargetScaler.fit(train_points, split="train")
    train_context_scaled = target_scaler.transform(train_windows.context)
    train_target_scaled = target_scaler.transform(train_windows.target)
    validation_context_scaled = target_scaler.transform(validation_windows.context)
    test_context_scaled = target_scaler.transform(test_windows.context)

    device = _resolve_device(args.device)
    model_document = _read_yaml(args.model_config)
    patch_config = dict(_mapping(model_document, "model"))
    patch_config["context_length"] = context_length
    patch_config["prediction_length"] = prediction_length
    raw_training = dict(_mapping(model_document, "training"))
    if args.max_epochs is not None:
        raw_training["max_epochs"] = args.max_epochs
    training_config = TorchTrainingConfig(
        seed=int(raw_training.get("seed", 42)),
        batch_size=int(raw_training.get("batch_size", 32)),
        max_epochs=int(raw_training.get("max_epochs", 15)),
        learning_rate=float(raw_training.get("learning_rate", 3e-4)),
        weight_decay=float(raw_training.get("weight_decay", 1e-4)),
        gradient_clip=float(raw_training.get("gradient_clip", 1.0)),
        early_stopping_patience=int(raw_training.get("early_stopping_patience", 4)),
        mixed_precision=bool(raw_training.get("mixed_precision", True)),
    )

    candidates: list[Candidate] = []
    for baseline in ("last_value", "seasonal_day", "seasonal_week"):
        validation_prediction = naive_predict(
            validation_windows.context,
            baseline,  # type: ignore[arg-type]
            prediction_length=prediction_length,
        )
        test_prediction = naive_predict(
            test_windows.context,
            baseline,  # type: ignore[arg-type]
            prediction_length=prediction_length,
        )
        candidates.append(
            Candidate(
                model_type=baseline,
                model=None,
                model_config={
                    "context_length": context_length,
                    "prediction_length": prediction_length,
                },
                training_config={"selection_split": "validation", "trainable": False},
                validation_prediction=validation_prediction,
                test_prediction=test_prediction,
                validation_mae=compute_forecast_metrics(
                    validation_windows.target, validation_prediction
                ).mae,
                best_epoch=None,
                training_seconds=0.0,
                peak_gpu_memory_bytes=None,
                history=[],
                selection={"rule": "deterministic baseline"},
            )
        )

    ridge, ridge_validation_mae, ridge_trials = select_and_fit_ridge(
        train_context_scaled,
        train_target_scaled,
        validation_context_scaled,
        validation_windows.target,
        scaler=target_scaler,
    )
    ridge_validation = np.maximum(
        0.0,
        target_scaler.inverse_transform(np.asarray(ridge.predict(validation_context_scaled))),
    )
    ridge_test = np.maximum(
        0.0,
        target_scaler.inverse_transform(np.asarray(ridge.predict(test_context_scaled))),
    )
    candidates.append(
        Candidate(
            model_type="ridge",
            model=ridge,
            model_config={
                "context_length": context_length,
                "prediction_length": prediction_length,
                "alpha": float(ridge.alpha),
            },
            training_config={"alpha_candidates": [0.1, 1.0, 10.0]},
            validation_prediction=ridge_validation,
            test_prediction=ridge_test,
            validation_mae=ridge_validation_mae,
            best_epoch=None,
            training_seconds=0.0,
            peak_gpu_memory_bytes=None,
            history=[],
            selection={"metric": "validation_mae", "trials": ridge_trials},
        )
    )

    lstm_config: dict[str, object] = {
        "context_length": context_length,
        "prediction_length": prediction_length,
        "hidden_size": 64,
        "num_layers": 1,
        "dropout": 0.0,
    }
    lstm = LSTMForecaster(
        prediction_length=prediction_length,
        hidden_size=int(lstm_config["hidden_size"]),
        num_layers=int(lstm_config["num_layers"]),
        dropout=float(lstm_config["dropout"]),
    )
    lstm_result = train_torch_model(
        lstm,
        train_context_scaled,
        train_target_scaled,
        validation_context_scaled,
        validation_windows.target,
        scaler=target_scaler,
        config=training_config,
        device=device,
        model_type="lstm",
    )
    candidates.append(
        _torch_candidate(
            "lstm",
            lstm,
            lstm_config,
            training_config,
            lstm_result,
            validation_context_scaled,
            test_context_scaled,
            target_scaler,
            device,
        )
    )
    if device.type == "cuda":
        torch.cuda.empty_cache()

    patchtst = build_patchtst(patch_config)
    patch_result = train_torch_model(
        patchtst,
        train_context_scaled,
        train_target_scaled,
        validation_context_scaled,
        validation_windows.target,
        scaler=target_scaler,
        config=training_config,
        device=device,
        model_type="patchtst",
    )
    candidates.append(
        _torch_candidate(
            "patchtst",
            patchtst,
            patch_config,
            training_config,
            patch_result,
            validation_context_scaled,
            test_context_scaled,
            target_scaler,
            device,
        )
    )

    code_commit = _git_commit(context.paths.root)
    experiment_id = utc_now().strftime("m4_%Y%m%d_%H%M%S")
    scaler_path = context.paths.root / "models" / "scalers" / experiment_id / "target_scaler.json"
    write_json(scaler_path, target_scaler.to_dict())
    scaler_hash = file_sha256(scaler_path)
    completed_at = utc_now()
    evaluated = [
        (
            candidate,
            compute_forecast_metrics(test_windows.target, candidate.test_prediction),
        )
        for candidate in candidates
    ]
    best_candidate, best_test_metrics = min(evaluated, key=lambda item: item[1].mae)
    naive_metrics = [
        metrics
        for candidate, metrics in evaluated
        if candidate.model_type in {"last_value", "seasonal_day", "seasonal_week"}
    ]
    patch_metrics = next(
        metrics for candidate, metrics in evaluated if candidate.model_type == "patchtst"
    )
    patch_improvement = max(
        max((metric.mae - patch_metrics.mae) / metric.mae, 0.0) if metric.mae > 0 else 0.0
        for metric in naive_metrics
    )

    registry_records: list[RegisteredModel] = []
    summary_rows: list[dict[str, object]] = []
    for candidate, test_metrics in evaluated:
        model_id = f"mdl_{candidate.model_type}_{experiment_id}"
        run_id = f"run_{experiment_id}_{candidate.model_type}"
        paths = registry_paths(context.paths.root, model_id)
        checkpoint_path = _checkpoint_path(context.paths.root, experiment_id, candidate.model_type)
        checkpoint_hash: str | None = None
        if candidate.model is not None:
            save_model(
                candidate.model,
                model_type=candidate.model_type,  # type: ignore[arg-type]
                path=checkpoint_path,
            )
            checkpoint_hash = file_sha256(checkpoint_path)
        quantiles = calibrate_conformal(
            validation_windows.target,
            candidate.validation_prediction,
            interval_level=context.settings.forecast.interval_level,
        )
        interval_result = interval_metrics(
            test_windows.target,
            candidate.test_prediction,
            quantiles,
        )
        inference_ms = _measure_inference_ms(
            candidate,
            test_windows.context[:1],
            test_context_scaled[:1],
            target_scaler,
            device,
        )
        metrics_document: dict[str, object] = {
            "schema_version": "1.0",
            "model_id": model_id,
            "run_id": run_id,
            "dataset_id": manifest.dataset_id,
            "preprocess_id": manifest.preprocess_id,
            "validation": compute_forecast_metrics(
                validation_windows.target, candidate.validation_prediction
            ).to_dict(),
            "test": test_metrics.to_dict(),
            "horizons": compute_horizon_metrics(test_windows.target, candidate.test_prediction),
            "steps": compute_step_metrics(test_windows.target, candidate.test_prediction),
            "interval": interval_result,
            "inference_latency_ms": inference_ms,
            "window_counts": _window_counts(train_windows, validation_windows, test_windows),
            "selection": candidate.selection,
            "training_history": candidate.history,
            "test_origin_count": len(test_windows.origins),
            "test_origins": [str(value) for value in test_windows.origins],
        }
        conformal_document = {
            "schema_version": "1.0",
            "method": "split_conformal_absolute_residual_per_horizon",
            "interval_level": context.settings.forecast.interval_level,
            "calibration_split": "validation",
            "calibration_windows": len(validation_windows.origins),
            "quantiles_kw": quantiles.astype(float).tolist(),
            "lower_bound_clip_kw": 0.0,
        }
        write_json(paths["metrics"], metrics_document)
        write_json(paths["conformal"], conformal_document)
        config_snapshot = {
            "window": {
                "context_length": context_length,
                "prediction_length": prediction_length,
                "train_stride": args.train_stride,
                "eval_stride": args.eval_stride,
            },
            "model": candidate.model_config,
            "training": candidate.training_config,
            "data_config_hash": manifest.config_hash,
        }
        is_default = candidate is best_candidate
        default_reason = (
            "固定测试起点下 MAE 最低；候选与参数已在测试前由验证集冻结。"
            if is_default
            else f"默认模型为 {DISPLAY_NAMES[best_candidate.model_type]}，其固定测试 MAE 更低。"
        )
        limitations = (
            "仅使用单个家庭 2007 年上半年数据，不能外推为其他家庭或当前年份表现。",
            "测试集只覆盖 2007 年 6 月，测试结果不用于重新训练或调参。",
            "90% 共形区间是时间序列上的经验覆盖，不是严格概率保证。",
        )
        record = RegisteredModel(
            model_id=model_id,
            run_id=run_id,
            model_type=candidate.model_type,  # type: ignore[arg-type]
            display_name=DISPLAY_NAMES[candidate.model_type],
            dataset_id=manifest.dataset_id,
            preprocess_id=manifest.preprocess_id,
            data_config_hash=manifest.config_hash,
            config_fingerprint=config_fingerprint(config_snapshot),
            context_length=context_length,
            prediction_length=prediction_length,
            interval_level=context.settings.forecast.interval_level,
            model_config_snapshot=candidate.model_config,
            training_config_snapshot=candidate.training_config,
            checkpoint_path_alias=(
                artifact_alias(checkpoint_path, project_root=context.paths.root)
                if candidate.model is not None
                else None
            ),
            checkpoint_sha256=checkpoint_hash,
            scaler_path_alias=artifact_alias(scaler_path, project_root=context.paths.root),
            scaler_sha256=scaler_hash,
            conformal_path_alias=artifact_alias(
                paths["conformal"], project_root=context.paths.root
            ),
            metrics_path_alias=artifact_alias(paths["metrics"], project_root=context.paths.root),
            model_card_path_alias=artifact_alias(paths["card"], project_root=context.paths.root),
            validation_mae=candidate.validation_mae,
            test_mae=test_metrics.mae,
            test_rmse=test_metrics.rmse,
            is_default=is_default,
            default_reason=default_reason,
            code_commit=code_commit,
            device=device.type if candidate.model_type in {"lstm", "patchtst"} else "cpu",
            training_seconds=candidate.training_seconds,
            peak_gpu_memory_bytes=candidate.peak_gpu_memory_bytes,
            created_at=completed_at,
            known_limitations=limitations,
        )
        write_json(paths["model"], record.model_dump(mode="json"))
        paths["card"].write_text(
            _model_card(record, metrics_document, interval_result), encoding="utf-8"
        )
        if candidate.model is not None:
            _verify_roundtrip(
                candidate,
                record,
                checkpoint_path,
                validation_context_scaled[:2],
                target_scaler,
                device,
            )
        register_model_run(
            context.paths.database_path,
            run_id=run_id,
            model_id=model_id,
            preprocess_id=manifest.preprocess_id,
            model_type=candidate.model_type,
            config_hash=record.config_fingerprint,
            device=record.device,
            best_epoch=candidate.best_epoch,
            metrics={
                "validation": metrics_document["validation"],
                "test": metrics_document["test"],
            },
            artifact_path_alias=artifact_alias(paths["root"], project_root=context.paths.root),
            started_at=completed_at,
            completed_at=completed_at,
        )
        registry_records.append(record)
        summary_rows.append(
            {
                "model_id": model_id,
                "model": DISPLAY_NAMES[candidate.model_type],
                "validation_mae": candidate.validation_mae,
                **test_metrics.to_dict(),
                "coverage": interval_result["coverage"],
                "average_width_kw": interval_result["average_width_kw"],
                "default": is_default,
            }
        )

    experiment_summary = {
        "schema_version": "1.0",
        "experiment_id": experiment_id,
        "dataset_id": manifest.dataset_id,
        "preprocess_id": manifest.preprocess_id,
        "data_config_hash": manifest.config_hash,
        "code_commit": code_commit,
        "device": str(device),
        "window_counts": _window_counts(train_windows, validation_windows, test_windows),
        "default_model_id": next(
            record.model_id for record in registry_records if record.is_default
        ),
        "patchtst_best_naive_mae_improvement": patch_improvement,
        "patchtst_meets_five_percent_gate": patch_improvement >= 0.05,
        "models": summary_rows,
        "created_at": completed_at,
    }
    write_json(
        context.paths.root / "models" / "registry" / f"{experiment_id}.json",
        experiment_summary,
    )
    print(json.dumps(experiment_summary, ensure_ascii=False, indent=2, default=str))


def _torch_candidate(
    model_type: str,
    model: torch.nn.Module,
    model_config: dict[str, object],
    training_config: TorchTrainingConfig,
    result: TrainingResult,
    validation_context_scaled: np.ndarray,
    test_context_scaled: np.ndarray,
    scaler: TargetScaler,
    device: torch.device,
) -> Candidate:
    validation_scaled = predict_torch(
        model,
        validation_context_scaled,
        device=device,
        model_type=model_type,  # type: ignore[arg-type]
        batch_size=training_config.batch_size,
    )
    test_scaled = predict_torch(
        model,
        test_context_scaled,
        device=device,
        model_type=model_type,  # type: ignore[arg-type]
        batch_size=training_config.batch_size,
    )
    return Candidate(
        model_type=model_type,
        model=model,
        model_config=model_config,
        training_config=asdict(training_config),
        validation_prediction=np.maximum(0.0, scaler.inverse_transform(validation_scaled)),
        test_prediction=np.maximum(0.0, scaler.inverse_transform(test_scaled)),
        validation_mae=result.validation_mae,
        best_epoch=result.best_epoch,
        training_seconds=result.training_seconds,
        peak_gpu_memory_bytes=result.peak_gpu_memory_bytes,
        history=[dict(row) for row in result.history],
        selection={"metric": "validation_mae", "early_stopping": True},
    )


def _verify_roundtrip(
    candidate: Candidate,
    record: RegisteredModel,
    checkpoint_path: Path,
    context_scaled: np.ndarray,
    scaler: TargetScaler,
    device: torch.device,
) -> None:
    loaded = load_model(
        model_type=candidate.model_type,  # type: ignore[arg-type]
        path=checkpoint_path,
        model_config=record.model_config_snapshot,
        device=device,
    )
    if candidate.model_type == "ridge":
        before_scaled = np.asarray(candidate.model.predict(context_scaled))  # type: ignore[union-attr]
        after_scaled = np.asarray(loaded.predict(context_scaled))  # type: ignore[union-attr]
    else:
        before_scaled = predict_torch(
            candidate.model,  # type: ignore[arg-type]
            context_scaled,
            device=device,
            model_type=candidate.model_type,  # type: ignore[arg-type]
        )
        after_scaled = predict_torch(
            loaded,  # type: ignore[arg-type]
            context_scaled,
            device=device,
            model_type=candidate.model_type,  # type: ignore[arg-type]
        )
    before = np.maximum(0.0, scaler.inverse_transform(before_scaled))
    after = np.maximum(0.0, scaler.inverse_transform(after_scaled))
    if not np.allclose(before, after, rtol=1e-5, atol=1e-5):
        raise RuntimeError(f"saved and loaded inference changed for {candidate.model_type}")


def _measure_inference_ms(
    candidate: Candidate,
    raw_context: np.ndarray,
    scaled_context: np.ndarray,
    scaler: TargetScaler,
    device: torch.device,
) -> float:
    started = torch.cuda.Event(enable_timing=True) if device.type == "cuda" else None
    ended = torch.cuda.Event(enable_timing=True) if device.type == "cuda" else None
    if started is not None and candidate.model_type in {"lstm", "patchtst"}:
        started.record()
        prediction = predict_torch(
            candidate.model,  # type: ignore[arg-type]
            scaled_context,
            device=device,
            model_type=candidate.model_type,  # type: ignore[arg-type]
        )
        ended.record()
        torch.cuda.synchronize(device)
        _ = scaler.inverse_transform(prediction)
        return float(started.elapsed_time(ended))
    import time

    clock = time.perf_counter()
    if candidate.model_type in {"last_value", "seasonal_day", "seasonal_week"}:
        naive_predict(raw_context, candidate.model_type, prediction_length=96)  # type: ignore[arg-type]
    elif candidate.model_type == "ridge":
        candidate.model.predict(scaled_context)  # type: ignore[union-attr]
    else:
        predict_torch(
            candidate.model,  # type: ignore[arg-type]
            scaled_context,
            device=device,
            model_type=candidate.model_type,  # type: ignore[arg-type]
        )
    return (time.perf_counter() - clock) * 1000.0


def _window_counts(*window_sets: Any) -> dict[str, object]:
    return {
        window.split: {
            "accepted": len(window.context),
            "candidates": window.candidate_count,
            "rejected": window.rejected_count,
            "rejection_reasons": window.rejection_reasons,
        }
        for window in window_sets
    }


def _checkpoint_path(root: Path, experiment_id: str, model_type: str) -> Path:
    suffix = ".joblib" if model_type == "ridge" else ".pt"
    return root / "models" / "checkpoints" / experiment_id / f"{model_type}{suffix}"


def _resolve_device(requested: str) -> torch.device:
    if requested == "cuda" and not torch.cuda.is_available():
        raise SystemExit("CUDA was explicitly requested but is unavailable")
    if requested == "cpu":
        return torch.device("cpu")
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def _read_yaml(path: Path) -> dict[str, object]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"model config must be a mapping: {path}")
    return {str(key): nested for key, nested in value.items()}


def _mapping(value: dict[str, object], key: str) -> dict[str, object]:
    nested = value.get(key)
    if not isinstance(nested, dict):
        raise ValueError(f"model config section is missing: {key}")
    return {str(item_key): item for item_key, item in nested.items()}


def _git_commit(root: Path) -> str:
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    dirty = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return f"{commit}+dirty" if dirty else commit


def _model_card(
    record: RegisteredModel,
    metrics: dict[str, object],
    interval_result: dict[str, object],
) -> str:
    test = metrics["test"]
    assert isinstance(test, dict)
    limitations = "\n".join(f"- {item}" for item in record.known_limitations)
    return f"""# {record.display_name} 模型卡

- model_id: `{record.model_id}`
- run_id: `{record.run_id}`
- dataset_id: `{record.dataset_id}`
- preprocess_id: `{record.preprocess_id}`
- 配置指纹: `{record.config_fingerprint}`
- 代码提交: `{record.code_commit}`
- 固定切分: 2007-01 至 04 月训练，05 月验证，06 月测试
- 窗口: {record.context_length} 点历史预测 {record.prediction_length} 点未来
- 训练设备: {record.device}
- 训练耗时: {record.training_seconds:.3f} 秒
- 默认模型: {"是" if record.is_default else "否"}；{record.default_reason}

## 固定测试集结果

| 指标 | 数值 |
| --- | ---: |
| MAE | {float(test["mae"]):.6f} kW |
| RMSE | {float(test["rmse"]):.6f} kW |
| WAPE | {float(test["wape"]):.4%} |
| sMAPE | {float(test["smape"]):.4%} |
| R² | {float(test["r2"]):.6f} |
| 90% 区间覆盖率 | {float(interval_result["coverage"]):.4%} |
| 平均区间宽度 | {float(interval_result["average_width_kw"]):.6f} kW |

## 限制

{limitations}
"""


if __name__ == "__main__":
    main()
