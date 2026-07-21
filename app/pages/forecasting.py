"""Planned load-forecasting page."""

from app.components.planned import render_planned_page

render_planned_page(
    title="负荷预测",
    purpose="在兼容模型和完整历史上下文就绪后，展示未来 24 小时预测、不确定性和真实测试指标。",
    requirement_ids=("FR-FCST-001", "FR-FCST-002", "FR-FCST-004", "FR-FCST-005"),
    capabilities=(
        "验证 672 点上下文并输出连续 96 个 15 分钟预测点",
        "比较朴素、Ridge、LSTM 与 PatchTST 的真实测试结果",
        "展示按预测步长校准的 90% 共形预测区间",
    ),
    dependencies=(
        "训练并注册至少一个与当前 preprocess_id 兼容的候选模型",
        "保存仅由训练集拟合的缩放器和可追踪模型卡",
        "在固定测试集完成指标与共形区间验收",
    ),
    guardrail="当前没有已训练模型、预测窗口、缩放器、预测曲线或模型指标；页面加载不会启动训练或推理。",
)
