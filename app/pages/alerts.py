"""Planned monitoring and alert page."""

from app.components.planned import render_planned_page

render_planned_page(
    title="监测预警",
    purpose="把数据质量、确定性规则和预测残差三类信号组织成可追踪、可解释的预警证据。",
    requirement_ids=("FR-ALERT-001", "FR-ALERT-002", "FR-ALERT-003", "FR-ALERT-004"),
    capabilities=(
        "把缺失、重复和时间断点转换为数据质量预警",
        "根据可追踪阈值生成确定性规则预警",
        "在预测与观测同时存在时计算残差预警",
    ),
    dependencies=(
        "冻结三类预警的稳定规则、证据字段和等级映射",
        "规则预警需要完成 M3 分析口径和阈值验收",
        "残差预警需要同一时间点的兼容预测和真实观测",
    ),
    guardrail=(
        "当前 M2 的 attention 只表示数据质量需关注，不代表完整预警业务已经启用，"
        "也不会提前生成规则或残差预警。"
    ),
)
