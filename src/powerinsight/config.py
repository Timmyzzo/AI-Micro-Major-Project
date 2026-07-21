"""Layered, validated application configuration."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

import yaml
from pydantic import BaseModel, Field, SecretStr, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from powerinsight.paths import PROJECT_ROOT

EnvironmentName = Literal["development", "test", "demo"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
DeviceName = Literal["auto", "cpu", "cuda"]

ENVIRONMENT_FIELDS: dict[str, str] = {
    "APP_ENV": "app_env",
    "APP_LOG_LEVEL": "app_log_level",
    "APP_DATA_DIR": "app_data_dir",
    "APP_ARTIFACT_DIR": "app_artifact_dir",
    "APP_DATABASE_PATH": "app_database_path",
    "DEVICE": "device",
    "MODEL_ID": "model_id",
    "LLM_ENABLED": "llm_enabled",
    "OPENAI_API_KEY": "openai_api_key",
    "OPENAI_BASE_URL": "openai_base_url",
    "OPENAI_MODEL": "openai_model",
    "OPENAI_TIMEOUT_SECONDS": "openai_timeout_seconds",
    "STREAMLIT_SERVER_PORT": "streamlit_server_port",
}
SENSITIVE_CONFIG_KEYS = {"api_key", "authorization", "openai_api_key"}
PROFILE_NAME_PATTERN = re.compile(r"^[a-z0-9_-]+$")


class ConfigurationError(ValueError):
    """Raised when a configuration source is missing, unsafe, or invalid."""


class DataSettings(BaseModel):
    """Data contract settings used by later milestones."""

    builtin_path: Path = Path("docs/household_power_consumption.csv")
    day_first: bool = True
    raw_cadence: str = "1min"
    target_cadence: str = "15min"
    short_gap_max_minutes: int = Field(default=60, ge=0)
    bucket_min_valid_ratio: float = Field(default=0.8, gt=0.0, le=1.0)
    unmetered_negative_tolerance_wh: float = Field(default=1e-9, ge=0.0)
    train_end: datetime = datetime(2007, 4, 30, 23, 59, 59)
    validation_end: datetime = datetime(2007, 5, 31, 23, 59, 59)
    test_end: datetime = datetime(2007, 6, 30, 23, 59, 59)


class ForecastSettings(BaseModel):
    """Forecast shape settings; no model is loaded or trained at this stage."""

    context_length: int = Field(default=672, ge=1)
    prediction_length: int = Field(default=96, ge=1)
    interval_level: float = Field(default=0.9, gt=0.0, lt=1.0)


class UiSettings(BaseModel):
    """Small set of display defaults shared by Streamlit pages."""

    language: str = "zh-CN"
    default_theme: Literal["light", "dark"] = "dark"
    max_chart_points: int = Field(default=10000, ge=100)


class AppSettings(BaseSettings):
    """Validated application settings with secrets excluded from serialization."""

    model_config = SettingsConfigDict(extra="forbid")

    app_env: EnvironmentName = "development"
    app_log_level: LogLevel = "INFO"
    app_data_dir: Path = Path("data")
    app_artifact_dir: Path = Path("artifacts")
    app_database_path: Path = Path("artifacts/powerinsight.db")
    device: DeviceName = "auto"
    model_id: str | None = None
    llm_enabled: bool = False
    openai_api_key: SecretStr | None = Field(default=None, repr=False, exclude=True)
    openai_base_url: str | None = None
    openai_model: str | None = None
    openai_timeout_seconds: float = Field(default=30.0, gt=0.0, le=300.0)
    streamlit_server_port: int = Field(default=8501, ge=1, le=65535)
    data: DataSettings = Field(default_factory=DataSettings)
    forecast: ForecastSettings = Field(default_factory=ForecastSettings)
    ui: UiSettings = Field(default_factory=UiSettings)
    config_sources: tuple[str, ...] = Field(default=("safe defaults",), exclude=True)

    @field_validator("app_log_level", mode="before")
    @classmethod
    def normalize_log_level(cls, value: object) -> object:
        """Normalize log levels before literal validation."""
        return value.upper() if isinstance(value, str) else value

    @field_validator("model_id", "openai_base_url", "openai_model", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: object) -> object:
        """Treat empty environment variables as unset optional values."""
        if isinstance(value, str) and not value.strip():
            return None
        return value.strip() if isinstance(value, str) else value

    @field_validator("app_data_dir", "app_artifact_dir", "app_database_path", mode="before")
    @classmethod
    def reject_empty_paths(cls, value: object) -> object:
        """Reject empty paths rather than resolving them to the project root."""
        if isinstance(value, str) and not value.strip():
            raise ValueError("path values must not be empty")
        return value

    @field_validator("openai_base_url")
    @classmethod
    def validate_base_url(cls, value: str | None) -> str | None:
        """Require an explicit HTTP(S) URL when a compatible endpoint is configured."""
        if value is None:
            return None
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("OPENAI_BASE_URL must be an absolute HTTP(S) URL")
        return value.rstrip("/")

    @model_validator(mode="after")
    def validate_llm_configuration(self) -> AppSettings:
        """Fail clearly when LLM use is enabled without its required secret and model."""
        if self.llm_enabled and self.openai_api_key is None:
            raise ValueError("LLM_ENABLED=true requires OPENAI_API_KEY")
        if self.llm_enabled and self.openai_model is None:
            raise ValueError("LLM_ENABLED=true requires OPENAI_MODEL")
        return self

    @property
    def llm_configured(self) -> bool:
        """Return whether LLM use is both enabled and complete without exposing the key."""
        return (
            self.llm_enabled and self.openai_api_key is not None and self.openai_model is not None
        )

    def safe_summary(self) -> dict[str, object]:
        """Return a non-sensitive settings summary suitable for diagnostics and UI."""
        return {
            "app_env": self.app_env,
            "app_log_level": self.app_log_level,
            "device": self.device,
            "model_id": self.model_id,
            "llm_enabled": self.llm_enabled,
            "llm_configured": self.llm_configured,
            "openai_base_url_configured": self.openai_base_url is not None,
            "openai_model": self.openai_model,
            "streamlit_server_port": self.streamlit_server_port,
            "config_sources": self.config_sources,
        }


def load_settings(
    *,
    profile: str | None = None,
    config_path: Path | None = None,
    runtime_overrides: Mapping[str, object] | None = None,
    environment: Mapping[str, str] | None = None,
    project_root: Path = PROJECT_ROOT,
) -> AppSettings:
    """Load defaults, YAML profile, environment, and runtime values in increasing priority."""
    environment_values = os.environ if environment is None else environment
    normalized_runtime = _normalize_overrides(runtime_overrides or {})
    selected_profile = _select_profile(profile, normalized_runtime, environment_values)

    merged: dict[str, Any] = {}
    sources = ["safe defaults"]

    default_path = (
        config_path.resolve()
        if config_path is not None and config_path.is_absolute()
        else project_root / (config_path or Path("configs/default.yaml"))
    )
    merged = _deep_merge(merged, _load_yaml(default_path, required=True))
    try:
        sources.append(default_path.resolve().relative_to(project_root.resolve()).as_posix())
    except ValueError:
        sources.append(f"external:{default_path.name}")

    if selected_profile is not None:
        profile_path = project_root / "configs" / f"{selected_profile}.yaml"
        merged = _deep_merge(merged, _load_yaml(profile_path, required=True))
        sources.append(f"configs/{selected_profile}.yaml")

    environment_overrides = {
        field_name: environment_values[environment_name]
        for environment_name, field_name in ENVIRONMENT_FIELDS.items()
        if environment_name in environment_values
    }
    if environment_overrides:
        merged = _deep_merge(merged, environment_overrides)
        sources.append("environment variables")

    if normalized_runtime:
        merged = _deep_merge(merged, normalized_runtime)
        sources.append("runtime overrides")

    merged["config_sources"] = tuple(sources)
    try:
        return AppSettings.model_validate(merged)
    except ValidationError as exc:
        raise ConfigurationError(f"Invalid PowerInsight configuration: {exc}") from exc


def _load_yaml(path: Path, *, required: bool) -> dict[str, Any]:
    if not path.is_file():
        if required:
            raise ConfigurationError(f"Configuration file does not exist: {path}")
        return {}
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigurationError(f"Unable to read configuration file {path}: {exc}") from exc
    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        raise ConfigurationError(f"Configuration file must contain a mapping: {path}")
    if _contains_sensitive_key(loaded):
        raise ConfigurationError(f"Secrets are not allowed in YAML configuration: {path}")
    return {str(key): value for key, value in loaded.items()}


def _contains_sensitive_key(value: object) -> bool:
    if isinstance(value, Mapping):
        for key, nested_value in value.items():
            if str(key).lower() in SENSITIVE_CONFIG_KEYS:
                return True
            if _contains_sensitive_key(nested_value):
                return True
    if isinstance(value, list):
        return any(_contains_sensitive_key(item) for item in value)
    return False


def _deep_merge(base: dict[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(base)
    for key, value in override.items():
        existing = result.get(key)
        if isinstance(existing, dict) and isinstance(value, Mapping):
            result[key] = _deep_merge(existing, value)
        else:
            result[key] = deepcopy(value)
    return result


def _normalize_overrides(values: Mapping[str, object]) -> dict[str, object]:
    return {ENVIRONMENT_FIELDS.get(key, key): value for key, value in values.items()}


def _select_profile(
    requested_profile: str | None,
    runtime_overrides: Mapping[str, object],
    environment: Mapping[str, str],
) -> str | None:
    candidate = requested_profile
    if candidate is None:
        runtime_environment = runtime_overrides.get("app_env")
        candidate = str(runtime_environment) if runtime_environment is not None else None
    if candidate is None:
        candidate = environment.get("APP_ENV")
    if candidate in {None, "", "development", "test"}:
        return None
    normalized = candidate.lower()
    if not PROFILE_NAME_PATTERN.fullmatch(normalized):
        raise ConfigurationError(f"Invalid configuration profile name: {candidate}")
    return normalized
