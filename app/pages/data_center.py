"""Planned data-center page."""

from app.components.planned import render_planned_page

render_planned_page(
    title="数据中心",
    purpose="后续用于内置/上传 CSV 的登记、字段校验、质量报告和预处理预览。",
    requirement_ids=("FR-DATA-001", "FR-DATA-002", "FR-DATA-004", "FR-DATA-005"),
    dependencies=("完成 M2 数据校验服务", "建立处理数据 manifest", "保持原始 CSV 只读"),
)
