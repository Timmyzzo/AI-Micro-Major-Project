"""Planned optimization-scenario page."""

from app.components.planned import render_planned_page

render_planned_page(
    title="优化决策",
    purpose="在用户明确参数和能量守恒约束下比较负荷转移情景，为后续决策提供可解释依据。",
    requirement_ids=("FR-OPT-001", "FR-OPT-002", "FR-OPT-004"),
    capabilities=(
        "配置峰、平、谷时段和用户输入电价",
        "模拟可转移负荷在允许时间窗内的重新分配",
        "比较峰值、峰谷差和费用并验证能量守恒",
    ),
    dependencies=(
        "获得具有明确口径的观测或预测负荷曲线",
        "实现并测试容量、时间窗和总能量守恒约束",
        "使用可手算夹具验证费用和负荷转移结果",
    ),
    guardrail="这是后续情景模拟而非真实控制；当前不生成成本、削峰比例、优化方案或任何看似可执行的设备指令。",
)
