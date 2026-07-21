"""Planned load-forecasting page."""

from app.components.planned import render_planned_page

render_planned_page(
    title="负荷预测",
    purpose="后续加载已训练模型，展示未来 24 小时点预测、区间和真实测试指标。",
    requirement_ids=("FR-FCST-001", "FR-FCST-002", "FR-FCST-004", "FR-FCST-005"),
    dependencies=("完成时间切分和处理数据", "训练并注册候选模型", "校准共形预测区间"),
)
