# 07 接口与存储契约

## 服务

| 服务 | 最小职责 |
| --- | --- |
| DataService | 固定 CSV 状态、校验和预处理 |
| AnalyticsService | 读取 15 分钟 Parquet 并计算分析结果 |
| ForecastService | 检查模型兼容性、推理、缓存和导出 |
| AlertService | 三类预警和 CSV 导出 |
| advice_service | 聚合摘要、大模型连接测试和一次建议调用 |

## 文件

~~~text
data/manifests/{dataset_id}.json
data/interim/{preprocess_id}/minute.parquet
data/processed/{preprocess_id}/power_15min.parquet
models/registry/{model_id}/*
artifacts/forecasts/{forecast_id}.json
artifacts/forecasts/{forecast_id}.csv
artifacts/powerinsight.db
~~~

## API 请求

只使用 `client.chat.completions.create(model=..., messages=...)`。请求包含 developer 约束和一个聚合 JSON user 消息。配置来自：

- `LLM_ENABLED`
- `OPENAI_API_KEY`
- `OPENAI_BASE_URL`（可选）
- `OPENAI_MODEL`
- `OPENAI_TIMEOUT_SECONDS`

Key 不得出现在请求正文、日志、SQLite、导出或页面。

接口形状以 OpenAI 官方 [Create chat completion](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create) 契约为准；兼容服务是否支持所选模型由用户配置和实际服务决定。

## 删除契约

不再定义 OptimizationRequest、ReportResult、报告 schema、Responses 参数、接口探测、alerts/optimization/reports 业务表或公共 REST 端点。现有数据库中的未用兼容表不承载新业务，也不要求迁移。
