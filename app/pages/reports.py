"""Planned evidence-constrained report page."""

from app.components.planned import render_planned_page

render_planned_page(
    title="智能报告",
    purpose="把已经计算并可追踪的证据整理为结构化中文报告，同时保留无需网络的本地模板回退。",
    requirement_ids=("FR-LLM-003", "FR-LLM-004", "FR-LLM-005", "FR-LLM-006"),
    capabilities=(
        "预览默认不含完整原始时序的脱敏证据包",
        "生成每项结论引用 evidence_id 的结构化报告",
        "在未配置、超时或响应无效时回退本地模板",
    ),
    dependencies=(
        "形成来自分析、预测、预警和优化的真实证据包",
        "实现接口适配、响应 schema 与数值一致性校验",
        "完成无需 API Key 的确定性模板报告和导出",
    ),
    guardrail=(
        "当前没有发起任何外部 API 请求，也不会要求提供 API Key、显示虚假连接状态，"
        "或生成无证据的分析报告。"
    ),
)
