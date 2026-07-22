"""Minimal deterministic summary plus one optional Chat Completions advice call."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Literal

from openai import OpenAI

from powerinsight.config import AppSettings
from powerinsight.services.analytics_service import AnalyticsService
from powerinsight.services.forecast_service import ForecastService
from powerinsight.services.runtime import RuntimeContext


@dataclass(frozen=True)
class AdviceSnapshot:
    """Small aggregate-only evidence sent to the optional external API."""

    evidence: dict[str, object]
    template: str


@dataclass(frozen=True)
class AdviceResult:
    """Short advice text and its generation mode."""

    text: str
    mode: Literal["api", "template"]
    diagnostic: str | None = None


@dataclass(frozen=True)
class LlmProbeResult:
    """User-triggered API connection result without secret disclosure."""

    status: Literal["success", "unconfigured", "failed"]
    model: str | None
    text: str | None = None
    latency_ms: float | None = None
    diagnostic: str | None = None


def build_advice_snapshot(context: RuntimeContext) -> AdviceSnapshot:
    """Build a compact summary from the current analytics and forecast results."""
    analytics = AnalyticsService(context)
    availability = analytics.inspect_availability()
    if (
        availability.status != "ready"
        or availability.manifest is None
        or availability.start_time is None
        or availability.end_time is None
    ):
        raise ValueError("verified analytics data is required")
    result = analytics.analyze(
        start=availability.start_time,
        end_exclusive=availability.end_time + timedelta(minutes=15),
    )
    forecast = ForecastService(context).inspect_availability()
    model = None
    if forecast.status == "ready":
        model = next(
            (item for item in forecast.models if item.is_default),
            forecast.models[0],
        )
    evidence: dict[str, object] = {
        "dataset_id": availability.manifest.dataset_id,
        "preprocess_id": availability.manifest.preprocess_id,
        "time_range": (
            f"{availability.start_time.isoformat()} / {availability.end_time.isoformat()}"
        ),
        "coverage_ratio": round(result.range_summary.coverage_ratio, 6),
        "total_energy_kwh": _rounded(result.kpis.total_active_energy_kwh),
        "average_power_kw": _rounded(result.kpis.average_active_power_kw),
        "peak_power_kw": _rounded(result.kpis.peak_active_power_kw),
        "peak_time": result.kpis.peak_time.isoformat() if result.kpis.peak_time else None,
        "default_model": model.display_name if model else None,
        "test_mae_kw": round(model.test_mae, 4) if model else None,
        "limitations": ["单户历史数据，仅代表当前分析范围"],
    }
    template = _template_advice(evidence)
    return AdviceSnapshot(evidence=evidence, template=template)


def generate_advice(
    snapshot: AdviceSnapshot,
    settings: AppSettings,
    *,
    client: Any | None = None,
) -> AdviceResult:
    """Make one detailed Chat Completions call, falling back to the local template."""
    if not settings.llm_configured:
        return AdviceResult(snapshot.template, "template", "not_configured")
    api_key = settings.openai_api_key
    model = settings.openai_model
    assert api_key is not None and model is not None
    try:
        api_client = _client(settings, client=client)
        response = api_client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "developer",
                    "content": (
                        "你是家庭用电智能分析助手。只能依据用户给出的聚合数据，"
                        "请用中文生成内容充实的分析建议，可写到约1000字，分为现状判断、"
                        "峰值管理、日常执行和持续观察四个部分。建议必须具体、可执行；"
                        "不得补造数值，不得把统计异常表述为电气故障。"
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(snapshot.evidence, ensure_ascii=False, sort_keys=True),
                },
            ],
        )
        content = response.choices[0].message.content
        if not isinstance(content, str) or not content.strip():
            raise ValueError("empty model response")
        return AdviceResult(content.strip(), "api")
    except Exception as exc:  # SDK maps transport and HTTP failures to safe fallback here.
        return AdviceResult(snapshot.template, "template", type(exc).__name__)


def probe_llm_connection(
    settings: AppSettings,
    *,
    client: Any | None = None,
) -> LlmProbeResult:
    """Send one minimal user-triggered message to verify the configured model."""
    if not settings.llm_configured:
        missing: list[str] = []
        if settings.openai_api_key is None:
            missing.append("API Key")
        if settings.openai_model is None:
            missing.append("模型")
        return LlmProbeResult(
            status="unconfigured",
            model=settings.openai_model,
            diagnostic="缺少" + "、".join(missing),
        )
    started = time.perf_counter()
    try:
        api_client = _client(settings, client=client)
        response = api_client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {
                    "role": "developer",
                    "content": "这是连接测试。请用中文回复一句简短确认，不要返回额外内容。",
                },
                {"role": "user", "content": "请确认大模型 API 连接正常。"},
            ],
        )
        content = response.choices[0].message.content
        if not isinstance(content, str) or not content.strip():
            raise ValueError("empty model response")
        return LlmProbeResult(
            status="success",
            model=settings.openai_model,
            text=content.strip(),
            latency_ms=(time.perf_counter() - started) * 1000.0,
        )
    except Exception as exc:
        return LlmProbeResult(
            status="failed",
            model=settings.openai_model,
            latency_ms=(time.perf_counter() - started) * 1000.0,
            diagnostic=type(exc).__name__,
        )


def _template_advice(evidence: dict[str, object]) -> str:
    average = evidence.get("average_power_kw")
    peak = evidence.get("peak_power_kw")
    peak_time = evidence.get("peak_time") or "未知时段"
    return (
        f"- 当前区间平均负荷约为 {average} kW，峰值约为 {peak} kW。\n"
        f"- 峰值出现在 {peak_time}，可优先复核该时段的高负荷用电。\n"
        "- 可结合峰值时段安排错峰用电，并持续观察负荷变化。"
    )


def _client(settings: AppSettings, *, client: Any | None) -> Any:
    if client is not None:
        return client
    api_key = settings.openai_api_key
    assert api_key is not None
    return OpenAI(
        api_key=api_key.get_secret_value(),
        base_url=settings.openai_base_url,
        timeout=settings.openai_timeout_seconds,
        max_retries=0,
    )


def _rounded(value: float | None) -> float | None:
    return round(value, 4) if value is not None else None
