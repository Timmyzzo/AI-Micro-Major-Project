"""Structured log redaction tests."""

from __future__ import annotations

import logging
from pathlib import Path

from powerinsight.config import AppSettings
from powerinsight.logging_config import configure_logging, get_logger
from powerinsight.paths import ProjectPaths


def test_logging_redacts_api_keys_and_authorization(tmp_path: Path) -> None:
    settings = AppSettings.model_validate({"app_log_level": "INFO"})
    paths = ProjectPaths(
        root=tmp_path,
        data_dir=tmp_path / "data",
        artifact_dir=tmp_path / "artifacts",
        database_path=tmp_path / "artifacts" / "test.db",
        log_dir=tmp_path / "logs",
        builtin_csv=tmp_path / "input.csv",
    )
    paths.ensure_runtime_directories()
    log_file = configure_logging(settings, paths)

    bearer_secret = "bearer-token-1234567890"
    api_secret = "sk-test-secret-value-1234567890"
    get_logger("test", request_id="req-1").warning(
        "Authorization: Bearer %s OPENAI_API_KEY=%s direct=%s",
        bearer_secret,
        api_secret,
        api_secret,
    )
    for handler in logging.getLogger("powerinsight").handlers:
        handler.flush()

    content = log_file.read_text(encoding="utf-8")
    assert bearer_secret not in content
    assert api_secret not in content
    assert "[REDACTED]" in content
    assert '"request_id": "req-1"' in content
