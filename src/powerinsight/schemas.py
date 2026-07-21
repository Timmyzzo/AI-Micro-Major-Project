"""Small shared schemas for the engineering skeleton."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class SystemStatus(BaseModel):
    """Non-sensitive runtime status rendered by the home and settings pages."""

    model_config = ConfigDict(frozen=True)

    python_version: str
    torch_version: str
    cuda_runtime: str | None
    cuda_available: bool
    gpu_name: str | None
    gpu_memory_bytes: int | None
    config_sources: tuple[str, ...]
    data_file_exists: bool
    data_status: str
    model_status: str
    database_accessible: bool
    database_status: str
    llm_enabled: bool
    llm_configured: bool
    llm_status: str
