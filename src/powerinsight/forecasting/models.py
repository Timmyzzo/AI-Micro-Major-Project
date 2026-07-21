"""Small Ridge, LSTM, and PatchTST training and inference helpers."""

from __future__ import annotations

import copy
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

import joblib  # type: ignore[import-untyped]
import numpy as np
import torch
from sklearn.linear_model import Ridge  # type: ignore[import-untyped]
from torch import nn
from torch.utils.data import DataLoader, TensorDataset
from transformers import PatchTSTConfig, PatchTSTForPrediction

from powerinsight.forecasting.core import TargetScaler, compute_forecast_metrics

TrainableModelName = Literal["ridge", "lstm", "patchtst"]


@dataclass(frozen=True)
class TorchTrainingConfig:
    """Shared deterministic training settings for the two small neural models."""

    seed: int = 42
    batch_size: int = 32
    max_epochs: int = 15
    learning_rate: float = 3e-4
    weight_decay: float = 1e-4
    gradient_clip: float = 1.0
    early_stopping_patience: int = 4
    mixed_precision: bool = True


@dataclass(frozen=True)
class TrainingResult:
    """Best validation state and measured training facts."""

    best_epoch: int
    epochs_completed: int
    validation_mae: float
    training_seconds: float
    peak_gpu_memory_bytes: int | None
    history: tuple[dict[str, float | int], ...]


class LSTMForecaster(nn.Module):
    """Small univariate LSTM with one direct 96-step projection head."""

    def __init__(
        self,
        *,
        prediction_length: int,
        hidden_size: int = 64,
        num_layers: int = 1,
        dropout: float = 0.0,
    ) -> None:
        super().__init__()
        self.prediction_length = prediction_length
        self.hidden_size = hidden_size
        self.num_layers = num_layers
        self.dropout = dropout
        self.lstm = nn.LSTM(
            input_size=1,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            dropout=dropout if num_layers > 1 else 0.0,
        )
        self.head = nn.Linear(hidden_size, prediction_length)

    def forward(self, values: torch.Tensor) -> torch.Tensor:
        encoded, _ = self.lstm(values.unsqueeze(-1))
        return cast(torch.Tensor, self.head(encoded[:, -1, :]))

    def config_dict(self) -> dict[str, object]:
        return {
            "prediction_length": self.prediction_length,
            "hidden_size": self.hidden_size,
            "num_layers": self.num_layers,
            "dropout": self.dropout,
        }


def build_patchtst(model_config: dict[str, object]) -> PatchTSTForPrediction:
    """Create the official single-channel Hugging Face PatchTST implementation."""
    config = PatchTSTConfig(
        num_input_channels=1,
        context_length=_config_int(model_config, "context_length"),
        prediction_length=_config_int(model_config, "prediction_length"),
        patch_length=_config_int(model_config, "patch_length", 16),
        patch_stride=_config_int(model_config, "patch_stride", 8),
        d_model=_config_int(model_config, "d_model", 64),
        num_attention_heads=_config_int(model_config, "num_attention_heads", 4),
        num_hidden_layers=_config_int(model_config, "num_hidden_layers", 3),
        ffn_dim=_config_int(model_config, "ffn_dim", 128),
        attention_dropout=_config_float(model_config, "dropout", 0.1),
        positional_dropout=_config_float(model_config, "dropout", 0.1),
        ff_dropout=_config_float(model_config, "dropout", 0.1),
        head_dropout=_config_float(model_config, "dropout", 0.1),
        loss="mse",
        scaling=False,
    )
    return PatchTSTForPrediction(config)


def select_and_fit_ridge(
    train_context: np.ndarray,
    train_target: np.ndarray,
    validation_context: np.ndarray,
    validation_target_kw: np.ndarray,
    *,
    scaler: TargetScaler,
    alpha_candidates: tuple[float, ...] = (0.1, 1.0, 10.0),
) -> tuple[Ridge, float, list[dict[str, float]]]:
    """Select Ridge alpha using validation MAE only and return the fitted candidate."""
    if not alpha_candidates:
        raise ValueError("at least one Ridge alpha candidate is required")
    trials: list[dict[str, float]] = []
    best_model: Ridge | None = None
    best_mae = float("inf")
    for alpha in alpha_candidates:
        model = Ridge(alpha=alpha)
        model.fit(train_context, train_target)
        prediction = np.maximum(
            0.0,
            scaler.inverse_transform(np.asarray(model.predict(validation_context))),
        )
        mae = compute_forecast_metrics(validation_target_kw, prediction).mae
        trials.append({"alpha": alpha, "validation_mae": mae})
        if mae < best_mae:
            best_mae = mae
            best_model = model
    assert best_model is not None
    return best_model, best_mae, trials


def train_torch_model(
    model: nn.Module,
    train_context: np.ndarray,
    train_target: np.ndarray,
    validation_context: np.ndarray,
    validation_target_kw: np.ndarray,
    *,
    scaler: TargetScaler,
    config: TorchTrainingConfig,
    device: torch.device,
    model_type: Literal["lstm", "patchtst"],
) -> TrainingResult:
    """Train with validation-only early stopping and restore the best weights."""
    set_reproducible_seed(config.seed)
    model.to(device)
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=config.learning_rate,
        weight_decay=config.weight_decay,
    )
    loss_function = nn.MSELoss()
    train_dataset = TensorDataset(
        torch.from_numpy(train_context.astype(np.float32, copy=False)),
        torch.from_numpy(train_target.astype(np.float32, copy=False)),
    )
    generator = torch.Generator().manual_seed(config.seed)
    loader = DataLoader(
        train_dataset,
        batch_size=config.batch_size,
        shuffle=True,
        num_workers=0,
        generator=generator,
    )
    amp_enabled = device.type == "cuda" and config.mixed_precision
    scaler_amp = torch.amp.GradScaler("cuda", enabled=amp_enabled)
    best_state: dict[str, torch.Tensor] | None = None
    best_mae = float("inf")
    best_epoch = 0
    epochs_without_improvement = 0
    history: list[dict[str, float | int]] = []
    if device.type == "cuda":
        torch.cuda.reset_peak_memory_stats(device)
    started = time.perf_counter()

    for epoch in range(1, config.max_epochs + 1):
        model.train()
        loss_sum = 0.0
        sample_count = 0
        for context_batch, target_batch in loader:
            context_batch = context_batch.to(device)
            target_batch = target_batch.to(device)
            optimizer.zero_grad(set_to_none=True)
            with torch.autocast(device_type=device.type, dtype=torch.float16, enabled=amp_enabled):
                prediction = _forward(model, context_batch, model_type=model_type)
                loss = loss_function(prediction, target_batch)
            scaler_amp.scale(loss).backward()
            scaler_amp.unscale_(optimizer)
            nn.utils.clip_grad_norm_(model.parameters(), config.gradient_clip)
            scaler_amp.step(optimizer)
            scaler_amp.update()
            loss_sum += float(loss.detach().cpu()) * len(context_batch)
            sample_count += len(context_batch)

        validation_prediction_scaled = predict_torch(
            model,
            validation_context,
            device=device,
            model_type=model_type,
            batch_size=config.batch_size,
        )
        validation_prediction_kw = np.maximum(
            0.0,
            scaler.inverse_transform(validation_prediction_scaled),
        )
        validation_mae = compute_forecast_metrics(
            validation_target_kw,
            validation_prediction_kw,
        ).mae
        history.append(
            {
                "epoch": epoch,
                "train_loss": loss_sum / max(sample_count, 1),
                "validation_mae": validation_mae,
            }
        )
        if validation_mae < best_mae - 1e-6:
            best_mae = validation_mae
            best_epoch = epoch
            best_state = copy.deepcopy(
                {key: value.detach().cpu() for key, value in model.state_dict().items()}
            )
            epochs_without_improvement = 0
        else:
            epochs_without_improvement += 1
            if epochs_without_improvement >= config.early_stopping_patience:
                break

    if best_state is None:
        raise RuntimeError("training did not produce a finite validation checkpoint")
    model.load_state_dict(best_state)
    model.to(device)
    training_seconds = time.perf_counter() - started
    peak_memory = int(torch.cuda.max_memory_allocated(device)) if device.type == "cuda" else None
    return TrainingResult(
        best_epoch=best_epoch,
        epochs_completed=len(history),
        validation_mae=best_mae,
        training_seconds=training_seconds,
        peak_gpu_memory_bytes=peak_memory,
        history=tuple(history),
    )


def predict_torch(
    model: nn.Module,
    context: np.ndarray,
    *,
    device: torch.device,
    model_type: Literal["lstm", "patchtst"],
    batch_size: int = 64,
) -> np.ndarray:
    """Run deterministic batched inference and return scaled two-dimensional outputs."""
    model.eval()
    batches: list[np.ndarray] = []
    with torch.inference_mode():
        for start in range(0, len(context), batch_size):
            values = torch.from_numpy(context[start : start + batch_size].astype(np.float32)).to(
                device
            )
            prediction = _forward(model, values, model_type=model_type)
            batches.append(prediction.detach().cpu().numpy().astype(np.float32))
    if not batches:
        raise ValueError("inference context is empty")
    return np.concatenate(batches, axis=0)


def save_model(model: object, *, model_type: TrainableModelName, path: Path) -> None:
    """Persist one fitted model below an ignored checkpoint directory."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if model_type == "ridge":
        joblib.dump(model, path)
        return
    if not isinstance(model, nn.Module):
        raise TypeError("torch model must be an nn.Module")
    torch.save(model.state_dict(), path)


def load_model(
    *,
    model_type: TrainableModelName,
    path: Path,
    model_config: dict[str, object],
    device: torch.device,
) -> object:
    """Load a model using its frozen registry configuration."""
    if not path.is_file():
        raise FileNotFoundError(path)
    if model_type == "ridge":
        return joblib.load(path)
    if model_type == "lstm":
        model: nn.Module = LSTMForecaster(
            prediction_length=_config_int(model_config, "prediction_length"),
            hidden_size=_config_int(model_config, "hidden_size", 64),
            num_layers=_config_int(model_config, "num_layers", 1),
            dropout=_config_float(model_config, "dropout", 0.0),
        )
    else:
        model = build_patchtst(model_config)
    state = torch.load(path, map_location="cpu", weights_only=True)
    model.load_state_dict(state)
    model.to(device)
    model.eval()
    return model


def set_reproducible_seed(seed: int) -> None:
    """Set all local random sources without promising cross-version bit identity."""
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.benchmark = False
    torch.use_deterministic_algorithms(True, warn_only=True)


def _forward(
    model: nn.Module,
    context: torch.Tensor,
    *,
    model_type: Literal["lstm", "patchtst"],
) -> torch.Tensor:
    if model_type == "lstm":
        return cast(torch.Tensor, model(context))
    output = model(past_values=context.unsqueeze(-1))
    prediction = cast(torch.Tensor, output.prediction_outputs)
    return prediction.squeeze(-1)


def _config_int(config: dict[str, object], key: str, default: int | None = None) -> int:
    value = config.get(key, default)
    if not isinstance(value, int | float):
        raise ValueError(f"model config {key} must be numeric")
    return int(value)


def _config_float(config: dict[str, object], key: str, default: float) -> float:
    value = config.get(key, default)
    if not isinstance(value, int | float):
        raise ValueError(f"model config {key} must be numeric")
    return float(value)
