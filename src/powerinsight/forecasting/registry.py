"""Versioned local model-registry contracts and safe JSON persistence."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, Field

from powerinsight.paths import display_path

ModelType = Literal[
    "last_value",
    "seasonal_day",
    "seasonal_week",
    "ridge",
    "lstm",
    "patchtst",
]


class RegisteredModel(BaseModel):
    """Small committed registry record pointing to reproducible local artifacts."""

    model_config = ConfigDict(frozen=True)

    schema_version: str = "1.0"
    model_id: str
    run_id: str
    model_type: ModelType
    display_name: str
    dataset_id: str
    preprocess_id: str
    data_config_hash: str
    config_fingerprint: str
    context_length: int = Field(ge=1)
    prediction_length: int = Field(ge=1)
    interval_level: float = Field(gt=0.0, lt=1.0)
    model_config_snapshot: dict[str, object]
    training_config_snapshot: dict[str, object]
    checkpoint_path_alias: str | None
    checkpoint_sha256: str | None
    scaler_path_alias: str
    scaler_sha256: str
    conformal_path_alias: str
    metrics_path_alias: str
    model_card_path_alias: str
    validation_mae: float
    test_mae: float
    test_rmse: float
    is_default: bool
    default_reason: str
    code_commit: str
    device: str
    training_seconds: float
    peak_gpu_memory_bytes: int | None
    created_at: datetime
    known_limitations: tuple[str, ...]


class RegistryError(ValueError):
    """Raised when a model registry entry is missing or incompatible."""


def config_fingerprint(value: dict[str, object]) -> str:
    """Hash a stable non-sensitive configuration snapshot."""
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest().upper()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def write_json(path: Path, value: object) -> None:
    """Atomically write indented UTF-8 JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=_json_default)
        + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def load_registered_model(path: Path) -> RegisteredModel:
    try:
        return RegisteredModel.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RegistryError(f"model registry entry is invalid: {path.name}: {exc}") from exc


def list_registered_models(registry_root: Path) -> tuple[RegisteredModel, ...]:
    """Load all valid registry entries without reading checkpoints."""
    if not registry_root.is_dir():
        return ()
    models: list[RegisteredModel] = []
    for path in sorted(registry_root.glob("mdl_*/model.json")):
        try:
            models.append(load_registered_model(path))
        except RegistryError:
            continue
    return tuple(models)


def registry_paths(project_root: Path, model_id: str) -> dict[str, Path]:
    root = project_root / "models" / "registry" / model_id
    return {
        "root": root,
        "model": root / "model.json",
        "metrics": root / "metrics.json",
        "conformal": root / "conformal.json",
        "card": root / "model_card.md",
    }


def artifact_alias(path: Path, *, project_root: Path) -> str:
    return display_path(path, root=project_root)


def utc_now() -> datetime:
    return datetime.now(UTC)


def _json_default(value: object) -> object:
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "item"):
        return cast(object, value.item())
    raise TypeError(f"not JSON serializable: {type(value).__name__}")
