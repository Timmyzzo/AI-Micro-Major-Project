"""Minimal deterministic summary plus one optional Chat Completions advice call."""

from __future__ import annotations

import json
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


def build_advice_snapshot(context: RuntimeContext) -> AdviceSnapshot:
    """Build a compact summary from verified M2-M4 results without raw time series."""
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
        "limitations": [
            "单户历史数据，不代表其他家庭",
            "统计异常不等于电气故障",
            "建议仅用于课程演示",
        ],
    }
    template = _template_advice(evidence)
    return AdviceSnapshot(evidence=evidence, template=template)


def generate_advice(
    snapshot: AdviceSnapshot,
    settings: AppSettings,
    *,
    client: Any | None = None,
) -> AdviceResult:
    """Make one short Chat Completions call, falling back to the local template."""
    if not settings.llm_configured:
        return AdviceResult(snapshot.template, "template", "not_configured")
    api_key = settings.openai_api_key
    model = settings.openai_model
    assert api_key is not None and model is not None
    try:
        api_client: Any = client or OpenAI(
            api_key=api_key.get_secret_value(),
            base_url=settings.openai_base_url,
            timeout=settings.openai_timeout_seconds,
            max_retries=0,
        )
        response = api_client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "developer",
                    "content": (
                        "你是家庭用电课程项目助手。只能依据用户给出的聚合数据，"
                        "用中文输出不超过三条简短建议；不得补造数值，不得声称电气故障，"
                        "结尾注明仅供课程演示。"
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


def _template_advice(evidence: dict[str, object]) -> str:
    average = evidence.get("average_power_kw")
    peak = evidence.get("peak_power_kw")
    peak_time = evidence.get("peak_time") or "未知时段"
    return (
        f"- 当前区间平均负荷约为 {average} kW，峰值约为 {peak} kW。\n"
        f"- 峰值出现在 {peak_time}，可优先复核该时段的高负荷用电。\n"
        "- 以上结论来自本地聚合数据，仅供课程演示，不作为电气安全或调度依据。"
    )


def _rounded(value: float | None) -> float | None:
    return round(value, 4) if value is not None else None
