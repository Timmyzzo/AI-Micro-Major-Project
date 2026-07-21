"""CPU forward, two-epoch smoke training, and persistence checks for M4 models."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import torch

from powerinsight.forecasting import TargetScaler
from powerinsight.forecasting.models import (
    LSTMForecaster,
    TorchTrainingConfig,
    build_patchtst,
    load_model,
    predict_torch,
    save_model,
    train_torch_model,
)


def _small_data() -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, TargetScaler]:
    rng = np.random.default_rng(42)
    context = rng.normal(size=(16, 32)).astype(np.float32)
    target = np.repeat(context[:, -1:], 8, axis=1) + 0.05
    scaler = TargetScaler.fit(context, split="train")
    return (
        scaler.transform(context[:12]),
        scaler.transform(target[:12]),
        scaler.transform(context[12:]),
        target[12:],
        scaler,
    )


def test_lstm_cpu_forward_shape() -> None:
    model = LSTMForecaster(prediction_length=8, hidden_size=8)
    prediction = predict_torch(
        model,
        np.ones((2, 32), dtype=np.float32),
        device=torch.device("cpu"),
        model_type="lstm",
    )
    assert prediction.shape == (2, 8)


def test_patchtst_cpu_forward_shape() -> None:
    model = build_patchtst(
        {
            "context_length": 32,
            "prediction_length": 8,
            "patch_length": 8,
            "patch_stride": 4,
            "d_model": 8,
            "num_attention_heads": 2,
            "num_hidden_layers": 1,
            "ffn_dim": 16,
            "dropout": 0.0,
        }
    )
    prediction = predict_torch(
        model,
        np.ones((2, 32), dtype=np.float32),
        device=torch.device("cpu"),
        model_type="patchtst",
    )
    assert prediction.shape == (2, 8)


def test_lstm_two_epoch_cpu_smoke_and_roundtrip(tmp_path: Path) -> None:
    train_x, train_y, validation_x, validation_y, scaler = _small_data()
    model = LSTMForecaster(prediction_length=8, hidden_size=8)
    config = TorchTrainingConfig(
        batch_size=4,
        max_epochs=2,
        early_stopping_patience=2,
        mixed_precision=False,
    )
    result = train_torch_model(
        model,
        train_x,
        train_y,
        validation_x,
        validation_y,
        scaler=scaler,
        config=config,
        device=torch.device("cpu"),
        model_type="lstm",
    )
    before = predict_torch(model, validation_x, device=torch.device("cpu"), model_type="lstm")
    path = tmp_path / "lstm.pt"
    save_model(model, model_type="lstm", path=path)
    loaded = load_model(
        model_type="lstm",
        path=path,
        model_config={"prediction_length": 8, "hidden_size": 8, "num_layers": 1},
        device=torch.device("cpu"),
    )
    after = predict_torch(
        loaded,  # type: ignore[arg-type]
        validation_x,
        device=torch.device("cpu"),
        model_type="lstm",
    )

    assert result.epochs_completed == 2
    assert np.isfinite(result.validation_mae)
    np.testing.assert_allclose(before, after, rtol=1e-6, atol=1e-6)


def test_patchtst_two_epoch_cpu_smoke_has_finite_loss() -> None:
    train_x, train_y, validation_x, validation_y, scaler = _small_data()
    model = build_patchtst(
        {
            "context_length": 32,
            "prediction_length": 8,
            "patch_length": 8,
            "patch_stride": 4,
            "d_model": 8,
            "num_attention_heads": 2,
            "num_hidden_layers": 1,
            "ffn_dim": 16,
            "dropout": 0.0,
        }
    )
    result = train_torch_model(
        model,
        train_x,
        train_y,
        validation_x,
        validation_y,
        scaler=scaler,
        config=TorchTrainingConfig(
            batch_size=4,
            max_epochs=2,
            early_stopping_patience=2,
            mixed_precision=False,
        ),
        device=torch.device("cpu"),
        model_type="patchtst",
    )

    assert result.epochs_completed == 2
    assert all(np.isfinite(float(row["train_loss"])) for row in result.history)
