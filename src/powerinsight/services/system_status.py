"""Collect non-sensitive system diagnostics without external calls or training."""

from __future__ import annotations

import platform

import torch

from powerinsight.config import AppSettings
from powerinsight.paths import ProjectPaths
from powerinsight.persistence.database import database_health
from powerinsight.schemas import SystemStatus


def collect_system_status(settings: AppSettings, paths: ProjectPaths) -> SystemStatus:
    """Collect current package, GPU, data, database, model, and LLM state."""
    cuda_available = torch.cuda.is_available()
    gpu_name: str | None = None
    gpu_memory_bytes: int | None = None
    if cuda_available:
        gpu_name = torch.cuda.get_device_name(0)
        gpu_memory_bytes = int(torch.cuda.get_device_properties(0).total_memory)

    database_accessible, database_status = database_health(paths.database_path)
    data_file_exists = paths.builtin_csv.is_file()
    data_status = "原始 CSV 可用，尚未处理" if data_file_exists else "原始 CSV 缺失"
    model_status = (
        f"已配置模型 ID {settings.model_id}，尚未验证权重"
        if settings.model_id
        else "尚未训练或注册模型"
    )
    if settings.llm_configured:
        llm_status = "已启用并完成配置，尚未发起连接测试"
    elif settings.llm_enabled:
        llm_status = "已启用但配置不完整"
    else:
        llm_status = "未启用；应用使用无密钥模式"

    return SystemStatus(
        python_version=platform.python_version(),
        torch_version=str(torch.__version__),
        cuda_runtime=torch.version.cuda,
        cuda_available=cuda_available,
        gpu_name=gpu_name,
        gpu_memory_bytes=gpu_memory_bytes,
        config_sources=settings.config_sources,
        data_file_exists=data_file_exists,
        data_status=data_status,
        model_status=model_status,
        database_accessible=database_accessible,
        database_status=database_status,
        llm_enabled=settings.llm_enabled,
        llm_configured=settings.llm_configured,
        llm_status=llm_status,
    )
