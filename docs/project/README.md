# 项目文档中心

本目录是项目需求、设计、验收和使用说明。当前产品展示 UCI 家庭用电数据分析、负荷预测、预警和外部大模型智能建议。

## 文档地图

| 编号 | 文档 | 内容 |
| --- | --- | --- |
| 01 | [项目范围](01-project-charter.md) | 最终目标与删除范围 |
| 02 | [需求](02-requirements-specification.md) | 保留的最小需求 |
| 03 | [页面](03-feature-and-ui-specification.md) | 七页信息架构 |
| 04 | [架构](04-system-architecture.md) | 简化模块与数据流 |
| 05 | [数据](05-data-specification.md) | 固定课程数据契约 |
| 06 | [模型与建议](06-model-and-intelligence-design.md) | 预测、区间、预警和 API 建议 |
| 07 | [接口与存储](07-interface-and-storage-contracts.md) | 最小服务和产物契约 |
| 08 | [环境](08-technology-and-environment.md) | Windows/Python/GPU/API 配置 |
| 09 | [开发规范](09-development-standards.md) | 编码、Git、测试与安全 |
| 10 | [测试验收](10-test-and-acceptance.md) | 已验证结果与剩余验收 |
| 11 | [演示](11-deployment-operations-demo.md) | 启动、演示和降级 |
| 12 | [计划](12-plan-risk-and-collaboration.md) | 当前进度和剩余任务 |
| 13 | [课程报告](13-course-report.md) | 两份最终 Word/PDF 报告与答辩 PPT |
| 14 | [决策](14-glossary-decisions-and-open-items.md) | 术语和范围决策 |
| 15 | [系统使用指南](15-system-usage-guide.md) | 安装、数据处理、训练、页面操作和排错 |
| 16 | [答辩界面优化](16-defense-ui-optimization.md) | 七页精简、API 状态与答辩验收清单 |

## 当前进度

当前代码已完成数据处理、历史分析、模型训练与测试、预测可视化、0.5 秒自动播放预警、首页大模型连接状态、真实智能建议调用和 Markdown 导出。答辩界面已按普通用户语言重构，七页最终截图、两份 DOCX/PDF 报告和 12 页答辩 PPT 均已完成视觉验收；根目录 BAT 脚本可双击启动系统。

## 当前边界

- 当前 UI 不提供上传 CSV、字段映射、多数据集和数据版本切换；允许在开发阶段选择其他公开电力数据，但必须适配契约并重建全部数据与模型产物；
- 优化决策页面、负荷转移、峰谷电价和多方案比较；
- 完整结构化智能报告、证据 ID 平台、HTML 导出和报告历史；
- Responses API、接口自动探测和复杂重试；
- 预警状态流转与备注；
- 新增 alerts/optimization/reports 数据库业务；
- REST API、Docker、云部署、多用户和真实设备。

采集、连续实时监测和优化决策不是本次课程核心验收前提，也不应在报告中描述为当前已实现能力。历史回放、预警和智能建议属于现有扩展展示。
