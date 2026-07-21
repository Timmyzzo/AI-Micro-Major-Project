"""Safe application bootstrap for Streamlit and diagnostic scripts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from powerinsight.config import AppSettings, load_settings
from powerinsight.logging_config import configure_logging, get_logger
from powerinsight.paths import PROJECT_ROOT, ProjectPaths
from powerinsight.persistence.database import initialize_database
from powerinsight.schemas import SystemStatus
from powerinsight.services.system_status import collect_system_status


@dataclass(frozen=True)
class RuntimeContext:
    """Validated settings, resolved paths, and current non-sensitive status."""

    settings: AppSettings
    paths: ProjectPaths
    status: SystemStatus


def initialize_runtime(
    *,
    profile: str | None = None,
    config_path: Path | None = None,
    runtime_overrides: Mapping[str, object] | None = None,
    project_root: Path = PROJECT_ROOT,
) -> RuntimeContext:
    """Initialize directories, logging, and metadata without training or external API calls."""
    settings = load_settings(
        profile=profile,
        config_path=config_path,
        runtime_overrides=runtime_overrides,
        project_root=project_root,
    )
    paths = ProjectPaths.from_settings(settings, root=project_root)
    paths.ensure_runtime_directories()
    configure_logging(settings, paths)
    database_info = initialize_database(paths.database_path)
    get_logger("runtime").info(
        "runtime_initialized",
        extra={"database_schema_version": database_info.schema_version},
    )
    status = collect_system_status(settings, paths)
    return RuntimeContext(settings=settings, paths=paths, status=status)
