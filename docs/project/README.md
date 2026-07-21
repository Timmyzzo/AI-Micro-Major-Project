# 项目文档中心

本目录是简化后的项目基线。项目只保留课程固定数据、确定性分析、负荷预测、预警和一个可选的大模型简短建议入口。

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
| 13 | [课程报告](13-course-report.md) | 最终 Word/PDF 内容 |
| 14 | [决策](14-glossary-decisions-and-open-items.md) | 术语和范围决策 |

## 当前进度

简化后的六个主要能力中，工程基础、固定数据、历史分析、模型预测、回放预警均已完成；智能建议的本地模板和 API 调用代码也已实现。剩余工作主要是最终截图、真实 API 可选验证和课程 Word/PDF 报告，因此整体进度已经明显超过一半。

## 已删除范围

- 上传 CSV、字段映射、多数据集和数据版本切换；
- 优化决策页面、负荷转移、峰谷电价和多方案比较；
- 完整结构化智能报告、证据 ID 平台、HTML 导出和报告历史；
- Responses API、接口自动探测和复杂重试；
- 预警状态流转与备注；
- 新增 alerts/optimization/reports 数据库业务；
- REST API、Docker、云部署、多用户和真实设备。

删除项不再是验收前提，也不应在报告中描述为已实现或待实现功能。
