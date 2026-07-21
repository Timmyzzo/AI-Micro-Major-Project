"""Configuration loading, priority, and secret-safety tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from powerinsight.config import ConfigurationError, load_settings
from powerinsight.paths import PROJECT_ROOT


def test_default_settings_load_without_api_key() -> None:
    settings = load_settings(environment={})

    assert settings.app_env == "development"
    assert settings.device == "auto"
    assert settings.openai_api_key is None
    assert settings.llm_enabled is False
    assert settings.llm_configured is False
    assert settings.data.builtin_path == Path("docs/household_power_consumption.csv")
    assert settings.config_sources == ("safe defaults", "configs/default.yaml")


def test_demo_profile_overrides_default_yaml() -> None:
    settings = load_settings(profile="demo", environment={})

    assert settings.app_env == "demo"
    assert settings.app_log_level == "WARNING"
    assert settings.ui.max_chart_points == 5000
    assert settings.config_sources[-1] == "configs/demo.yaml"


def test_environment_overrides_yaml_and_parses_types() -> None:
    settings = load_settings(
        environment={
            "APP_LOG_LEVEL": "error",
            "APP_DATA_DIR": "custom-data",
            "STREAMLIT_SERVER_PORT": "9100",
        }
    )

    assert settings.app_log_level == "ERROR"
    assert settings.app_data_dir == Path("custom-data")
    assert settings.streamlit_server_port == 9100
    assert settings.config_sources[-1] == "environment variables"


def test_runtime_overrides_have_highest_priority() -> None:
    settings = load_settings(
        profile="demo",
        environment={"APP_LOG_LEVEL": "ERROR"},
        runtime_overrides={"APP_LOG_LEVEL": "DEBUG", "STREAMLIT_SERVER_PORT": 9200},
    )

    assert settings.app_log_level == "DEBUG"
    assert settings.streamlit_server_port == 9200
    assert settings.config_sources[-1] == "runtime overrides"


def test_api_key_is_excluded_from_repr_dump_and_safe_summary() -> None:
    secret = "sk-test-secret-value-1234567890"
    settings = load_settings(
        environment={
            "OPENAI_API_KEY": secret,
            "LLM_ENABLED": "false",
        }
    )

    rendered = "\n".join(
        (
            repr(settings),
            str(settings),
            str(settings.safe_summary()),
            settings.model_dump_json(),
        )
    )
    assert secret not in rendered
    assert "openai_api_key" not in settings.model_dump()


def test_enabled_llm_requires_key_and_model() -> None:
    with pytest.raises(ConfigurationError, match="requires OPENAI_API_KEY"):
        load_settings(
            environment={
                "LLM_ENABLED": "true",
                "OPENAI_MODEL": "example-model",
            }
        )


def test_yaml_rejects_api_key(tmp_path: Path) -> None:
    config_dir = tmp_path / "configs"
    config_dir.mkdir()
    (config_dir / "default.yaml").write_text(
        "app_env: development\nopenai_api_key: should-not-be-here\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError, match="Secrets are not allowed"):
        load_settings(environment={}, project_root=tmp_path)


def test_invalid_profile_name_is_rejected() -> None:
    with pytest.raises(ConfigurationError, match="Invalid configuration profile name"):
        load_settings(profile="../secret", environment={}, project_root=PROJECT_ROOT)


def test_explicit_config_file_is_supported(tmp_path: Path) -> None:
    config_path = tmp_path / "custom.yaml"
    config_path.write_text(
        "app_env: test\ndata:\n  builtin_path: docs/custom.csv\n  short_gap_max_minutes: 30\n",
        encoding="utf-8",
    )

    settings = load_settings(
        config_path=config_path,
        environment={},
        project_root=tmp_path,
    )

    assert settings.data.builtin_path == Path("docs/custom.csv")
    assert settings.data.short_gap_max_minutes == 30
    assert settings.config_sources == ("safe defaults", "custom.yaml")
