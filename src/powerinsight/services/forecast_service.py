"""Load-only M4 forecast service with compatibility checks and offline caching."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Protocol, cast

import numpy as np
import pandas as pd  # type: ignore[import-untyped]
import torch

from powerinsight.forecasting import TargetScaler, naive_predict
from powerinsight.forecasting.models import load_model, predict_torch
from powerinsight.forecasting.registry import (
    RegisteredModel,
    file_sha256,
    list_registered_models,
    write_json,
)
from powerinsight.paths import display_path
from powerinsight.persistence.metadata import register_forecast
from powerinsight.services.data_service import DataService
from powerinsight.services.runtime import RuntimeContext

ForecastStatus = Literal["completed", "cached"]
AvailabilityStatus = Literal["ready", "blocked"]


class _Predictor(Protocol):
    def predict(self, values: np.ndarray) -> object: ...


@dataclass(frozen=True)
class ForecastAvailability:
    status: AvailabilityStatus
    title: str
    reason: str
    evidence: tuple[str, ...]
    next_step: str
    models: tuple[RegisteredModel, ...] = ()
    origins: tuple[datetime, ...] = ()


@dataclass(frozen=True)
class ForecastResult:
    forecast_id: str
    status: ForecastStatus
    model: RegisteredModel
    forecast_start: datetime
    device: str
    latency_ms: float
    created_at: datetime
    context: pd.DataFrame
    forecast: pd.DataFrame
    metrics: dict[str, object]
    cache_path_alias: str

    def export_frame(self) -> pd.DataFrame:
        """Return a stable CSV contract with complete non-sensitive metadata."""
        frame = self.forecast.copy()
        frame["forecast_id"] = self.forecast_id
        frame["model_id"] = self.model.model_id
        frame["run_id"] = self.model.run_id
        frame["dataset_id"] = self.model.dataset_id
        frame["preprocess_id"] = self.model.preprocess_id
        frame["config_fingerprint"] = self.model.config_fingerprint
        frame["interval_level"] = self.model.interval_level
        frame["generated_at"] = self.created_at.isoformat()
        frame["result_status"] = self.status
        frame["device"] = self.device
        return frame[
            [
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
            ]
        ]


class ForecastError(RuntimeError):
    """Display-safe forecast failure with stable code and recovery guidance."""

    def __init__(
        self,
        *,
        code: str,
        title: str,
        reason: str,
        evidence: tuple[str, ...] = (),
        next_step: str,
    ) -> None:
        super().__init__(reason)
        self.code = code
        self.title = title
        self.reason = reason
        self.evidence = evidence
        self.next_step = next_step


class ForecastService:
    """Validate registry artifacts and run inference without training in Streamlit."""

    def __init__(self, context: RuntimeContext) -> None:
        self._context = context

    def inspect_availability(self) -> ForecastAvailability:
        """Inspect M2 data, compatible M4 registry entries, and fixed test origins."""
        state = DataService(self._context).inspect_builtin_state()
        if state.manifest is None or not state.processed_exists:
            return ForecastAvailability(
                status="blocked",
                title="M2 预测数据依赖不可用",
                reason="当前缺少可验证的 manifest 或 15 分钟 Parquet。",
                evidence=("FCST_DATA_UNAVAILABLE",),
                next_step="先在数据中心完成内置数据校验与预处理。",
            )
        registry_root = self._context.paths.root / "models" / "registry"
        models = tuple(
            model
            for model in list_registered_models(registry_root)
            if self._is_compatible(model, state.manifest.preprocess_id, state.manifest.config_hash)
        )
        if not models:
            return ForecastAvailability(
                status="blocked",
                title="没有与当前数据兼容的 M4 模型",
                reason="页面不会训练模型，也不会用计划值伪造预测。",
                evidence=(state.manifest.preprocess_id, "MODEL_COMPATIBLE_ARTIFACT_MISSING"),
                next_step="在命令行运行 scripts/train_m4.py，并保留生成的本地模型产物。",
            )
        origins = self._available_origins(state.manifest.preprocess_id)
        if not origins:
            return ForecastAvailability(
                status="blocked",
                title="固定测试集没有合格预测起点",
                reason="所有起点都必须具有 672 个连续有效历史点和 96 个真实未来点。",
                evidence=("FCST_INSUFFICIENT_HISTORY",),
                next_step="检查 M2 Parquet、长缺失掩码和固定月份切分。",
            )
        ordered = tuple(sorted(models, key=lambda item: (not item.is_default, item.test_mae)))
        return ForecastAvailability(
            status="ready",
            title="M4 模型与固定测试起点可用",
            reason="页面只加载冻结模型并推理；训练、早停和测试评估均在命令行完成。",
            evidence=(
                state.manifest.preprocess_id,
                f"兼容模型 {len(ordered)} 个",
                f"测试起点 {len(origins)} 个",
            ),
            next_step="选择起点、模型和设备后运行即时预测，或允许复用离线缓存。",
            models=ordered,
            origins=origins,
        )

    def predict(
        self,
        *,
        model_id: str,
        forecast_start: datetime,
        requested_device: Literal["auto", "cpu", "cuda"],
        allow_cache: bool,
    ) -> ForecastResult:
        """Run or load one compatible backtest forecast at a fixed test origin."""
        availability = self.inspect_availability()
        if availability.status != "ready":
            raise ForecastError(
                code="FCST_BLOCKED",
                title=availability.title,
                reason=availability.reason,
                evidence=availability.evidence,
                next_step=availability.next_step,
            )
        model = next((item for item in availability.models if item.model_id == model_id), None)
        if model is None:
            raise ForecastError(
                code="MODEL_NOT_REGISTERED",
                title="所选模型不可用",
                reason="模型不存在或与当前 dataset_id、preprocess_id、窗口契约不兼容。",
                evidence=(model_id,),
                next_step="重新选择页面列出的兼容模型。",
            )
        normalized_start = pd.Timestamp(forecast_start).to_pydatetime()
        if normalized_start not in availability.origins:
            raise ForecastError(
                code="FCST_INSUFFICIENT_HISTORY",
                title="预测起点没有完整上下文",
                reason="该起点不属于冻结的日级非重叠测试起点集合。",
                evidence=(normalized_start.isoformat(),),
                next_step="选择页面提供的测试起点。",
            )
        request_hash = self._request_hash(model, normalized_start, requested_device)
        forecast_id = f"fcst_{request_hash[:16].lower()}"
        cache_json = self._context.paths.artifact_dir / "forecasts" / f"{forecast_id}.json"
        cache_csv = self._context.paths.artifact_dir / "forecasts" / f"{forecast_id}.csv"
        if allow_cache and cache_json.is_file():
            return self._load_cache(cache_json, model)

        context_frame, future_frame = self._load_window(model.preprocess_id, normalized_start)
        raw_context = (
            context_frame["global_active_power_kw"].to_numpy(dtype=np.float32).reshape(1, -1)
        )
        scaler = (
            None
            if model.model_type in {"last_value", "seasonal_day", "seasonal_week"}
            else self._load_scaler(model)
        )
        scaled_context = raw_context if scaler is None else scaler.transform(raw_context)
        actual_device = self._resolve_device(model, requested_device)
        started = time.perf_counter()
        prediction = self._predict_model(model, raw_context, scaled_context, scaler, actual_device)
        latency_ms = (time.perf_counter() - started) * 1000.0
        quantiles = self._load_quantiles(model)
        lower = np.maximum(0.0, prediction - quantiles)
        upper = prediction + quantiles
        truth = future_frame["global_active_power_kw"].to_numpy(dtype=np.float32)
        outside = (truth < lower) | (truth > upper)
        forecast = pd.DataFrame(
            {
                "timestamp": future_frame["timestamp"].to_numpy(),
                "y_pred_kw": prediction,
                "lower_kw": lower,
                "upper_kw": upper,
                "y_true_kw": truth,
                "is_outside_interval": outside,
            }
        )
        created_at = datetime.now(UTC)
        metrics = self.load_metrics(model)
        cache_alias = display_path(cache_json, root=self._context.paths.root)
        payload = {
            "schema_version": "1.0",
            "forecast_id": forecast_id,
            "request_hash": request_hash,
            "status": "completed",
            "model_id": model.model_id,
            "dataset_id": model.dataset_id,
            "preprocess_id": model.preprocess_id,
            "config_fingerprint": model.config_fingerprint,
            "forecast_start": normalized_start,
            "device": actual_device.type,
            "latency_ms": latency_ms,
            "created_at": created_at,
            "context": _frame_records(context_frame),
            "forecast": _frame_records(forecast),
        }
        write_json(cache_json, payload)
        result = ForecastResult(
            forecast_id=forecast_id,
            status="completed",
            model=model,
            forecast_start=normalized_start,
            device=actual_device.type,
            latency_ms=latency_ms,
            created_at=created_at,
            context=context_frame,
            forecast=forecast,
            metrics=metrics,
            cache_path_alias=cache_alias,
        )
        result.export_frame().to_csv(cache_csv, index=False, encoding="utf-8-sig")
        register_forecast(
            self._context.paths.database_path,
            forecast_id=forecast_id,
            dataset_id=model.dataset_id,
            model_id=model.model_id,
            forecast_start=normalized_start,
            request_hash=request_hash,
            status="completed",
            artifact_path_alias=cache_alias,
            latency_ms=latency_ms,
            created_at=created_at,
        )
        return result

    def load_metrics(self, model: RegisteredModel) -> dict[str, object]:
        path = self._resolve_alias(model.metrics_path_alias)
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ForecastError(
                code="MODEL_METRICS_INVALID",
                title="模型指标不可读取",
                reason="冻结指标文件缺失或格式无效。",
                evidence=(model.model_id,),
                next_step="重新运行 M4 训练与注册脚本。",
            ) from exc
        if not isinstance(value, dict) or value.get("model_id") != model.model_id:
            raise ForecastError(
                code="MODEL_METRICS_INCOMPATIBLE",
                title="模型指标身份不一致",
                reason="指标文件没有绑定到所选模型。",
                evidence=(model.model_id,),
                next_step="重新生成该模型的注册产物。",
            )
        return {str(key): nested for key, nested in value.items()}

    def comparison_frame(self, models: tuple[RegisteredModel, ...]) -> pd.DataFrame:
        rows: list[dict[str, object]] = []
        for model in models:
            metrics = self.load_metrics(model)
            test = metrics.get("test")
            interval = metrics.get("interval")
            if not isinstance(test, dict) or not isinstance(interval, dict):
                continue
            rows.append(
                {
                    "模型": model.display_name,
                    "MAE（kW）": test.get("mae"),
                    "RMSE（kW）": test.get("rmse"),
                    "WAPE": test.get("wape"),
                    "sMAPE": test.get("smape"),
                    "R²": test.get("r2"),
                    "覆盖率": interval.get("coverage"),
                    "平均区间宽度（kW）": interval.get("average_width_kw"),
                    "默认": "是" if model.is_default else "否",
                }
            )
        return pd.DataFrame(rows)

    def _is_compatible(
        self,
        model: RegisteredModel,
        preprocess_id: str,
        data_config_hash: str,
    ) -> bool:
        return (
            model.schema_version == "1.0"
            and model.dataset_id.startswith("ds_")
            and model.preprocess_id == preprocess_id
            and model.data_config_hash == data_config_hash
            and model.context_length == self._context.settings.forecast.context_length
            and model.prediction_length == self._context.settings.forecast.prediction_length
            and model.interval_level == self._context.settings.forecast.interval_level
        )

    def _available_origins(self, preprocess_id: str) -> tuple[datetime, ...]:
        frame = self._read_processed(preprocess_id)
        test = frame.loc[frame["split"].eq("test")].sort_values("timestamp").reset_index(drop=True)
        context_length = self._context.settings.forecast.context_length
        prediction_length = self._context.settings.forecast.prediction_length
        origins: list[datetime] = []
        for origin in range(context_length, len(test) - prediction_length + 1, prediction_length):
            window = test.iloc[origin - context_length : origin + prediction_length]
            if self._window_is_valid(window):
                origins.append(pd.Timestamp(test.iloc[origin]["timestamp"]).to_pydatetime())
        return tuple(origins)

    def _load_window(
        self,
        preprocess_id: str,
        forecast_start: datetime,
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        frame = self._read_processed(preprocess_id)
        test = frame.loc[frame["split"].eq("test")].sort_values("timestamp").reset_index(drop=True)
        matches = test.index[test["timestamp"].eq(pd.Timestamp(forecast_start))].tolist()
        if len(matches) != 1:
            raise ForecastError(
                code="FCST_START_NOT_FOUND",
                title="预测起点不在测试数据中",
                reason="处理后 Parquet 与页面起点不一致。",
                next_step="刷新页面并重新选择起点。",
            )
        origin = matches[0]
        context_length = self._context.settings.forecast.context_length
        prediction_length = self._context.settings.forecast.prediction_length
        window = test.iloc[origin - context_length : origin + prediction_length].copy()
        if len(window) != context_length + prediction_length or not self._window_is_valid(window):
            raise ForecastError(
                code="FCST_INSUFFICIENT_HISTORY",
                title="上下文或真实未来不完整",
                reason="窗口包含缺失、长缺失或不连续时间戳。",
                next_step="改用页面列出的其他固定测试起点。",
            )
        context_frame = window.iloc[:context_length][
            ["timestamp", "global_active_power_kw"]
        ].reset_index(drop=True)
        future_frame = window.iloc[context_length:][
            ["timestamp", "global_active_power_kw"]
        ].reset_index(drop=True)
        return context_frame, future_frame

    def _read_processed(self, preprocess_id: str) -> pd.DataFrame:
        path = self._context.paths.data_dir / "processed" / preprocess_id / "power_15min.parquet"
        try:
            return pd.read_parquet(
                path,
                columns=["timestamp", "global_active_power_kw", "long_gap", "split"],
            )
        except (OSError, ValueError) as exc:
            raise ForecastError(
                code="FCST_PARQUET_UNREADABLE",
                title="15 分钟预测数据不可读取",
                reason="Parquet 缺失、损坏或列契约不兼容。",
                evidence=(display_path(path, root=self._context.paths.root),),
                next_step="重新运行 M2 预处理并使旧模型缓存失效。",
            ) from exc

    @staticmethod
    def _window_is_valid(window: pd.DataFrame) -> bool:
        values = window["global_active_power_kw"].to_numpy(dtype=np.float64)
        long_gap = window["long_gap"].fillna(True).to_numpy(dtype=bool)
        timestamps = pd.to_datetime(window["timestamp"]).to_numpy(dtype="datetime64[ns]")
        return bool(
            np.isfinite(values).all()
            and not long_gap.any()
            and np.all(np.diff(timestamps) == np.timedelta64(15, "m"))
        )

    def _load_scaler(self, model: RegisteredModel) -> TargetScaler:
        path = self._resolve_alias(model.scaler_path_alias)
        if not path.is_file() or file_sha256(path) != model.scaler_sha256:
            raise self._artifact_error(model, "MODEL_SCALER_MISMATCH", "缩放器缺失或哈希不一致")
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(value, dict):
                raise ValueError("scaler JSON is not an object")
            return TargetScaler.from_dict(value)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise self._artifact_error(model, "MODEL_SCALER_INVALID", "缩放器契约不可读取") from exc

    def _load_quantiles(self, model: RegisteredModel) -> np.ndarray:
        path = self._resolve_alias(model.conformal_path_alias)
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(value, dict) or value.get("interval_level") != model.interval_level:
                raise ValueError("interval level changed")
            quantiles = np.asarray(value["quantiles_kw"], dtype=np.float32)
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
            raise self._artifact_error(
                model, "MODEL_INTERVAL_INVALID", "共形区间产物不可读取"
            ) from exc
        if quantiles.shape != (model.prediction_length,) or not np.isfinite(quantiles).all():
            raise self._artifact_error(model, "MODEL_INTERVAL_INVALID", "共形分位数 shape 无效")
        return np.asarray(quantiles, dtype=np.float32)

    def _predict_model(
        self,
        model: RegisteredModel,
        raw_context: np.ndarray,
        scaled_context: np.ndarray,
        scaler: TargetScaler | None,
        device: torch.device,
    ) -> np.ndarray:
        if model.model_type in {"last_value", "seasonal_day", "seasonal_week"}:
            prediction = naive_predict(
                raw_context,
                model.model_type,
                prediction_length=model.prediction_length,
            )[0]
            return np.asarray(prediction, dtype=np.float32)
        if scaler is None:
            raise self._artifact_error(model, "MODEL_SCALER_MISSING", "可训练模型没有缩放器")
        if model.checkpoint_path_alias is None or model.checkpoint_sha256 is None:
            raise self._artifact_error(model, "MODEL_CHECKPOINT_MISSING", "模型权重路径未注册")
        checkpoint = self._resolve_alias(model.checkpoint_path_alias)
        if not checkpoint.is_file() or file_sha256(checkpoint) != model.checkpoint_sha256:
            raise self._artifact_error(
                model, "MODEL_CHECKPOINT_MISMATCH", "模型权重缺失或哈希不一致"
            )
        loaded = load_model(
            model_type=model.model_type,  # type: ignore[arg-type]
            path=checkpoint,
            model_config=model.model_config_snapshot,
            device=device,
        )
        if model.model_type == "ridge":
            predictor = cast(_Predictor, loaded)
            scaled_prediction = np.asarray(predictor.predict(scaled_context), dtype=np.float32)
        else:
            scaled_prediction = predict_torch(
                loaded,  # type: ignore[arg-type]
                scaled_context,
                device=device,
                model_type=model.model_type,  # type: ignore[arg-type]
            )
        return np.asarray(
            np.maximum(0.0, scaler.inverse_transform(scaled_prediction)[0]),
            dtype=np.float32,
        )

    def _resolve_device(
        self,
        model: RegisteredModel,
        requested: Literal["auto", "cpu", "cuda"],
    ) -> torch.device:
        if model.model_type in {"last_value", "seasonal_day", "seasonal_week", "ridge"}:
            return torch.device("cpu")
        if requested == "cuda" and not torch.cuda.is_available():
            raise ForecastError(
                code="MODEL_CUDA_UNAVAILABLE",
                title="CUDA 当前不可用",
                reason="用户明确选择了 CUDA，但 PyTorch 未检测到可用 GPU。",
                next_step="选择 CPU，或修复 CUDA 环境后重试。",
            )
        if requested == "cpu":
            return torch.device("cpu")
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")

    def _load_cache(self, path: Path, model: RegisteredModel) -> ForecastResult:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            if (
                not isinstance(value, dict)
                or value.get("model_id") != model.model_id
                or value.get("preprocess_id") != model.preprocess_id
                or value.get("config_fingerprint") != model.config_fingerprint
            ):
                raise ValueError("cache identity changed")
            context = pd.DataFrame(value["context"])
            forecast = pd.DataFrame(value["forecast"])
            context["timestamp"] = pd.to_datetime(context["timestamp"])
            forecast["timestamp"] = pd.to_datetime(forecast["timestamp"])
            forecast["is_outside_interval"] = forecast["is_outside_interval"].astype(bool)
            created_at = datetime.fromisoformat(str(value["created_at"]))
            forecast_start = datetime.fromisoformat(str(value["forecast_start"]))
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise ForecastError(
                code="FCST_CACHE_INVALID",
                title="预测缓存不可用",
                reason="缓存身份、格式或内容无效；没有静默使用损坏结果。",
                evidence=(display_path(path, root=self._context.paths.root),),
                next_step="关闭缓存控制后重新运行即时预测。",
            ) from exc
        return ForecastResult(
            forecast_id=str(value["forecast_id"]),
            status="cached",
            model=model,
            forecast_start=forecast_start,
            device=str(value["device"]),
            latency_ms=float(value["latency_ms"]),
            created_at=created_at,
            context=context,
            forecast=forecast,
            metrics=self.load_metrics(model),
            cache_path_alias=display_path(path, root=self._context.paths.root),
        )

    def _request_hash(
        self,
        model: RegisteredModel,
        forecast_start: datetime,
        requested_device: str,
    ) -> str:
        payload = {
            "schema_version": "1.0",
            "dataset_id": model.dataset_id,
            "preprocess_id": model.preprocess_id,
            "model_id": model.model_id,
            "config_fingerprint": model.config_fingerprint,
            "forecast_start": forecast_start.isoformat(),
            "interval_level": model.interval_level,
            "requested_device": requested_device,
        }
        serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def _resolve_alias(self, alias: str) -> Path:
        path = (self._context.paths.root / alias).resolve()
        try:
            path.relative_to(self._context.paths.root.resolve())
        except ValueError as exc:
            raise ForecastError(
                code="MODEL_ARTIFACT_PATH_UNSAFE",
                title="模型产物路径不安全",
                reason="注册产物指向项目目录之外，已拒绝读取。",
                next_step="重新生成不含绝对路径的模型注册记录。",
            ) from exc
        return path

    @staticmethod
    def _artifact_error(model: RegisteredModel, code: str, reason: str) -> ForecastError:
        return ForecastError(
            code=code,
            title="模型产物不完整或不兼容",
            reason=reason,
            evidence=(model.model_id, model.config_fingerprint),
            next_step="重新运行 M4 训练脚本，且不要手工混用模型、缩放器或区间文件。",
        )


def _frame_records(frame: pd.DataFrame) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for row in frame.to_dict(orient="records"):
        records.append(
            {
                str(key): value.isoformat() if isinstance(value, pd.Timestamp) else value
                for key, value in row.items()
            }
        )
    return records
