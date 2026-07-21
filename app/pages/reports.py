"""Planned evidence-constrained report page."""

from app.components.planned import render_planned_page

render_planned_page(
    title="智能报告",
    purpose="后续把确定性分析证据转换为结构化中文报告，并提供本地模板回退。",
    requirement_ids=("FR-LLM-003", "FR-LLM-004", "FR-LLM-005", "FR-LLM-006"),
    dependencies=("形成可追踪证据包", "实现响应 schema 校验", "提供无需 API 的模板报告"),
)
