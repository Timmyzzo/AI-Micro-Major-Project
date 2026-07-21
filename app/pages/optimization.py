"""Planned optimization-scenario page."""

from app.components.planned import render_planned_page

render_planned_page(
    title="优化决策",
    purpose="后续进行峰谷电价与可转移负荷情景模拟，不连接或控制真实设备。",
    requirement_ids=("FR-OPT-001", "FR-OPT-002", "FR-OPT-004"),
    dependencies=("获得可用负荷曲线", "实现能量守恒约束", "建立可手算验收夹具"),
)
