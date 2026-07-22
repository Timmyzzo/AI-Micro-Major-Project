"""Collect non-sensitive system diagnostics without external calls or training."""

from __future__ import annotations

import platform

import torch

from powerinsight.config import AppSettings
from powerinsight.data.catalog import build_dataset_id, compute_sha256
from powerinsight.forecasting.registry import list_registered_models
from powerinsight.paths import ProjectPaths, display_path
from powerinsight.persistence.database import database_health
from powerinsight.schemas import DatasetManifest, SystemStatus


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
    if data_file_exists:
        source_alias = display_path(paths.builtin_csv, root=paths.root)
        source_sha256 = compute_sha256(paths.builtin_csv)
        dataset_id = build_dataset_id(source_alias, source_sha256)
        manifest_path = paths.data_dir / "manifests" / f"{dataset_id}.json"
        if manifest_path.is_file():
            try:
                manifest = DatasetManifest.model_validate_json(
                    manifest_path.read_text(encoding="utf-8")
                )
                processed_path = (
                    paths.data_dir / "processed" / manifest.preprocess_id / "power_15min.parquet"
                )
                data_status = (
                    "分析数据已就绪"
                    if manifest.source_sha256 == source_sha256 and processed_path.is_file()
                    else "处理产物不完整或已失效"
                )
            except (OSError, ValueError):
                data_status = "manifest 不可读取，需要重新生成"
        else:
            data_status = "原始 CSV 可用，尚未处理"
    else:
        data_status = "原始 CSV 缺失"
    registered_models = list_registered_models(paths.root / "models" / "registry")
    default_model = next((model for model in registered_models if model.is_default), None)
    if default_model is not None:
        model_status = (
            f"已加载 {len(registered_models)} 个预测模型；推荐 {default_model.display_name}"
        )
    elif registered_models:
        model_status = f"已加载 {len(registered_models)} 个预测模型"
    elif settings.model_id:
        model_status = f"已配置模型 ID {settings.model_id}，尚未验证权重"
    else:
        model_status = "尚未训练或注册模型"
    if settings.llm_configured:
        llm_status = "已配置，等待连接测试"
    elif settings.llm_enabled:
        llm_status = "已启用，等待补充连接信息"
    else:
        llm_status = "未启用"

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
