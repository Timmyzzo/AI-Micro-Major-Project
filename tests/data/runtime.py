"""Temporary RuntimeContext factory for service and Streamlit integration tests."""

from __future__ import annotations

from pathlib import Path

from powerinsight.config import AppSettings
from powerinsight.paths import ProjectPaths
from powerinsight.schemas import SystemStatus
from powerinsight.services.runtime import RuntimeContext


def make_runtime_context(tmp_path: Path) -> RuntimeContext:
    """Create an isolated context with no external calls or project runtime artifacts."""
    settings = AppSettings.model_validate(
        {
            "app_data_dir": "data",
            "app_artifact_dir": "artifacts",
            "app_database_path": "artifacts/test.db",
            "data": {"builtin_path": "docs/input.csv"},
        }
    )
    paths = ProjectPaths.from_settings(settings, root=tmp_path)
    paths.ensure_runtime_directories()
    status = SystemStatus(
        python_version="3.11",
        torch_version="test",
        cuda_runtime=None,
        cuda_available=False,
        gpu_name=None,
        gpu_memory_bytes=None,
        config_sources=("test",),
        data_file_exists=True,
        data_status="test",
        model_status="test",
        database_accessible=True,
        database_status="test",
        llm_enabled=False,
        llm_configured=False,
        llm_status="test",
    )
    return RuntimeContext(settings=settings, paths=paths, status=status)
