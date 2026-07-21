"""Structured console and rotating-file logging with secret redaction."""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from powerinsight.config import AppSettings
    from powerinsight.paths import ProjectPaths

REDACTION_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"(?i)(authorization\s*[:=]\s*)(?:bearer\s+)?[^\s,;]+"),
        r"\1[REDACTED]",
    ),
    (
        re.compile(r"(?i)((?:openai_)?api[_-]?key\s*[:=]\s*)[^\s,;]+"),
        r"\1[REDACTED]",
    ),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b"), "[REDACTED]"),
)


def redact_text(value: str) -> str:
    """Remove common API-key and Authorization representations from text."""
    redacted = value
    for pattern, replacement in REDACTION_RULES:
        redacted = pattern.sub(replacement, redacted)
    return redacted


class JsonLogFormatter(logging.Formatter):
    """Render a stable JSON object with optional request and run identifiers."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": redact_text(record.getMessage()),
        }
        for field_name in ("request_id", "run_id", "dataset_id", "model_id"):
            field_value = getattr(record, field_name, None)
            if field_value is not None:
                payload[field_name] = redact_text(str(field_value))
        if record.exc_info:
            payload["exception"] = redact_text(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(settings: AppSettings, paths: ProjectPaths) -> Path:
    """Configure idempotent structured logging and return the active log file path."""
    paths.log_dir.mkdir(parents=True, exist_ok=True)
    log_file = paths.log_dir / "powerinsight.log"
    formatter = JsonLogFormatter()

    application_logger = logging.getLogger("powerinsight")
    application_logger.setLevel(getattr(logging, settings.app_log_level))
    application_logger.propagate = False
    application_logger.handlers.clear()

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    application_logger.addHandler(console_handler)

    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=2 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    application_logger.addHandler(file_handler)
    return log_file


def get_logger(
    name: str,
    *,
    request_id: str | None = None,
    run_id: str | None = None,
) -> logging.LoggerAdapter[logging.Logger]:
    """Return a logger adapter with optional tracing fields."""
    extra = {
        key: value for key, value in {"request_id": request_id, "run_id": run_id}.items() if value
    }
    return logging.LoggerAdapter(logging.getLogger(f"powerinsight.{name}"), extra)
