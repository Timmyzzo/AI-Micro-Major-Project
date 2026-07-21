"""Planned electric-use analytics page."""

from app.components.planned import render_planned_page

render_planned_page(
    title="用电分析",
    purpose="后续展示有明确单位与统计口径的历史趋势、周期规律和分项用电结构。",
    requirement_ids=("FR-MON-001", "FR-MON-002", "FR-MON-003", "FR-MON-004"),
    dependencies=("完成 15 分钟聚合", "实现确定性 KPI 服务", "通过数据质量检查"),
)
