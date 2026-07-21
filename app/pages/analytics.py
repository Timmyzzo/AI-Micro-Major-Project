"""Planned electric-use analytics page."""

from app.components.planned import render_planned_page

render_planned_page(
    title="用电分析",
    purpose="理解历史负荷如何随时间变化，并在明确单位、区间和缺失口径下识别周期规律。",
    requirement_ids=("FR-MON-001", "FR-MON-002", "FR-MON-003", "FR-MON-004"),
    capabilities=(
        "按日期范围和粒度查看总负荷及相关测量趋势",
        "比较小时、星期和工作日/周末规律",
        "解释分项用电结构并输出确定性摘要",
    ),
    dependencies=(
        "实现并测试 M3 确定性 KPI 与分析服务",
        "大范围查询必须使用 15 分钟聚合或下采样",
        "所有指标明确单位、时间范围、聚合口径和缺失说明",
    ),
    guardrail=(
        "当前不计算正式 KPI，不绘制趋势、热力图或分项图，也不把 M2 数据质量摘要包装成用电分析结论。"
    ),
)
