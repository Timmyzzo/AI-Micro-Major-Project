"""Planned monitoring and alert page."""

from app.components.planned import render_planned_page

render_planned_page(
    title="监测预警",
    purpose="后续展示数据质量、确定性规则和预测残差三类预警及其证据。",
    requirement_ids=("FR-ALERT-001", "FR-ALERT-002", "FR-ALERT-003", "FR-ALERT-004"),
    dependencies=("完成数据质量规则", "产生兼容预测结果", "冻结可追踪的预警阈值"),
)
