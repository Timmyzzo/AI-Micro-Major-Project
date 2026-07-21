# 07 接口与存储契约

## 1. 目的

MVP 不建设公开 REST 服务。本文档定义 Streamlit 页面与领域服务之间的内部契约、文件产物、SQLite 元数据和 OpenAI 兼容接口。后续若增加 FastAPI，必须复用这些领域对象，而不是重新定义一套不兼容格式。

## 2. 版本规则

- 数据 schema：data_schema_version，初始计划 1.0；
- 模型 schema：model_schema_version，初始计划 1.0；
- 预测 schema：forecast_schema_version，初始计划 1.0；
- 报告 schema：report_schema_version，初始计划 1.0；
- 主版本变化表示不兼容；
- 次版本变化只能增加可选字段；
- 读取旧产物时先校验版本，不能静默猜测。

## 3. 标识符

| 对象 | 格式示例 | 生成依据 |
| --- | --- | --- |
| dataset_id | ds_2007h1_c79e3e19 | 数据别名与源指纹 |
| preprocess_id | prep_20260721_001 | 数据与处理配置 |
| run_id | run_20260721_153012_ab12 | 时间与随机后缀 |
| model_id | mdl_patchtst_runid | 模型类型与运行 |
| forecast_id | fcst_runid_timestamp | 模型与预测起点 |
| alert_id | alt_type_timestamp_hash | 类型、时间和证据 |
| scenario_id | opt_timestamp_hash | 输入情景 |
| report_id | rpt_timestamp_hash | evidence_hash 和时间 |

ID 不包含 API Key、完整绝对路径或个人信息。

## 4. 服务边界

### 4.1 DataCatalogService

| 操作 | 输入 | 输出 | 失败 |
| --- | --- | --- | --- |
| register_dataset | 文件引用、来源类型 | DatasetRecord | 文件不存在、不可读 |
| get_dataset | dataset_id | DatasetRecord | 未找到 |
| list_datasets | 筛选条件 | DatasetRecord 列表 | 存储不可用 |
| verify_fingerprint | dataset_id | 是否一致 | 文件改变 |

### 4.2 DataValidationService

| 操作 | 输入 | 输出 |
| --- | --- | --- |
| inspect_header | 文件引用 | 字段、编码、分隔符、样本 |
| validate | dataset_id、映射配置 | DataQualityReport |
| find_missing_blocks | 规范数据 | MissingBlock 列表 |
| infer_cadence | 时间戳 | 频率和置信度 |

### 4.3 PreprocessingService

| 操作 | 输入 | 输出 |
| --- | --- | --- |
| prepare | dataset_id、PreprocessConfig | ProcessedDatasetRecord |
| preview | 数据区间、配置 | 原始/处理后对比 |
| build_windows | preprocess_id、WindowConfig、split | 窗口数据集 |

### 4.4 AnalyticsService

| 操作 | 输入 | 输出 |
| --- | --- | --- |
| calculate_kpis | preprocess_id、时间范围 | KPI 列表 |
| load_profile | 粒度、分组 | 曲线与分位数 |
| submeter_breakdown | 时间范围 | 分项与未分项电量 |
| representative_days | 规则 | 日期及曲线 |
| evidence_summary | 分析结果 | Evidence 列表 |

### 4.5 ForecastService

| 操作 | 输入 | 输出 |
| --- | --- | --- |
| list_models | 兼容条件 | ModelRecord 列表 |
| validate_context | 数据、起点、模型 | 可用性与原因 |
| predict | ForecastRequest | ForecastResult |
| backtest | 模型、窗口集合 | EvaluationResult |
| export | forecast_id、格式 | 导出文件 |

### 4.6 AlertService

| 操作 | 输入 | 输出 |
| --- | --- | --- |
| evaluate_quality | 质量报告 | Alert 列表 |
| evaluate_rules | 观测、规则配置 | Alert 列表 |
| evaluate_residual | 观测、预测、区间 | Alert 列表 |
| list_alerts | 筛选条件 | Alert 列表 |
| update_status | alert_id、状态、备注 | 更新后的 Alert |

### 4.7 OptimizationService

| 操作 | 输入 | 输出 |
| --- | --- | --- |
| validate_scenario | OptimizationRequest | 校验结果 |
| simulate | OptimizationRequest | OptimizationResult |
| compare | scenario_id 列表 | 对比表 |

### 4.8 LLMReportService

| 操作 | 输入 | 输出 |
| --- | --- | --- |
| test_connection | 非敏感配置 | ConnectionTestResult |
| build_evidence | 对象 ID 列表 | EvidenceBundle |
| preview_payload | EvidenceBundle | 脱敏 JSON |
| generate | ReportRequest | ReportResult |
| fallback | EvidenceBundle、错误类别 | ReportResult |

## 5. 主要领域对象

### 5.1 DatasetRecord

| 字段 | 类型 | 必需 | 说明 |
| --- | --- | --- | --- |
| schema_version | 字符串 | 是 | 对象版本 |
| dataset_id | 字符串 | 是 | 唯一 ID |
| name | 字符串 | 是 | 展示名称 |
| source_type | 枚举 | 是 | built_in 或 upload |
| path_alias | 字符串 | 是 | 非敏感路径别名 |
| sha256 | 字符串 | 是 | 文件指纹 |
| size_bytes | 整数 | 是 | 文件大小 |
| row_count | 整数 | 是 | 数据行数 |
| start_time | 时间 | 否 | 校验后填入 |
| end_time | 时间 | 否 | 校验后填入 |
| cadence | 字符串 | 否 | 例如 1min |
| status | 枚举 | 是 | registered、validated、invalid |
| created_at | 时间 | 是 | 注册时间 |

### 5.2 DataQualityReport

| 字段 | 说明 |
| --- | --- |
| dataset_id | 数据 ID |
| validation_version | 规则版本 |
| status | usable、attention、blocked |
| score | 0 至 100，可为空 |
| row_count | 行数 |
| parsed_timestamp_count | 成功时间戳 |
| duplicate_count | 重复 |
| cadence_violations | 间隔异常 |
| missing_cells_by_column | 各列缺失 |
| missing_blocks | 缺失区段 |
| issues | 错误、警告、信息 |
| generated_at | 时间 |

### 5.3 ForecastRequest

~~~json
{
  "schema_version": "1.0",
  "dataset_id": "ds_2007h1_c79e3e19",
  "preprocess_id": "prep_example",
  "model_id": "mdl_patchtst_example",
  "forecast_start": "2007-06-15T00:00:00",
  "context_points": 672,
  "prediction_points": 96,
  "interval_level": 0.9,
  "device": "auto",
  "allow_cache": true
}
~~~

示例中的模型和处理 ID 不是当前已存在产物。

### 5.4 ForecastResult

| 字段 | 说明 |
| --- | --- |
| forecast_id | 预测 ID |
| request | 请求快照 |
| status | completed、cached、failed |
| timestamps | 96 个时间戳 |
| y_pred_kw | 点预测 |
| lower_kw / upper_kw | 区间 |
| interval_method | 共形配置 |
| latency_ms | 推理耗时 |
| device | 实际设备 |
| created_at | 生成时间 |
| warnings | 上下文质量或兼容性提示 |

### 5.5 Alert

| 字段 | 说明 |
| --- | --- |
| alert_id | 预警 ID |
| alert_type | data_quality、rule、residual |
| severity | info、attention、critical |
| start_time / end_time | 时间范围 |
| title | 简短标题 |
| observed | 观测值对象 |
| expected | 预测或阈值对象 |
| score | 异常分数 |
| evidence_ids | 证据 |
| dataset_id / model_id | 来源 |
| rule_version | 规则版本 |
| status | open、acknowledged、ignored |
| note | 本地备注 |
| created_at / updated_at | 时间 |

### 5.6 OptimizationRequest

| 字段 | 说明 |
| --- | --- |
| source_type | observation 或 forecast |
| source_id | 数据或预测 ID |
| target_date | 目标日期 |
| tariff_periods | 时间段和价格 |
| flexible_meter | 分项字段或用户指定比例 |
| flexible_ratio | 0 至 1 |
| allowed_windows | 允许目标窗口 |
| max_delay_slots | 最大延迟 |
| max_added_kw | 每槽最大新增负荷 |
| objective | cost、peak 或 balanced |
| solver | greedy 或 linear_program |

### 5.7 ReportResult

| 字段 | 说明 |
| --- | --- |
| report_id | 报告 ID |
| generation_mode | llm 或 template |
| evidence_hash | 证据指纹 |
| provider_alias | 提供商别名，不含 Key |
| model_alias | 模型名 |
| structured_content | 校验后的报告对象 |
| markdown_path | 导出路径 |
| status | completed、fallback、failed |
| diagnostics | 脱敏错误类别 |
| created_at | 时间 |

## 6. 文件产物布局

~~~text
data/manifests/{dataset_id}.json
data/interim/{preprocess_id}/minute.parquet
data/processed/{preprocess_id}/power_15min.parquet
models/checkpoints/{run_id}/best.safetensors
models/scalers/{run_id}/target_scaler.json
models/registry/{model_id}/model_card.md
models/registry/{model_id}/metrics.json
artifacts/forecasts/{forecast_id}.csv
artifacts/forecasts/{forecast_id}.json
artifacts/exports/{export_id}.csv
artifacts/reports/{report_id}.md
artifacts/demo/demo_manifest.json
logs/app-YYYY-MM-DD.jsonl
~~~

实际文件名应经过安全清理，不能直接使用用户上传文件名拼接路径。

## 7. 预测 CSV 导出契约

列顺序：

1. timestamp；
2. y_pred_kw；
3. lower_kw；
4. upper_kw；
5. y_true_kw，可选，仅回测；
6. is_outside_interval，可选；
7. forecast_id；
8. model_id；
9. dataset_id；
10. generated_at。

第一行表头使用英文稳定字段名；界面另提供中文说明。

## 8. 预警 CSV 导出契约

至少包含：

- alert_id；
- alert_type；
- severity；
- start_time；
- end_time；
- metric；
- observed_value；
- expected_lower；
- expected_upper；
- threshold；
- score；
- status；
- dataset_id；
- model_id；
- rule_version；
- created_at。

所有文本字段在导出前进行 CSV 公式注入防护。

## 9. SQLite 设计

数据库计划位置：artifacts/powerinsight.db。

### 9.1 datasets

| 列 | 类型 | 约束 |
| --- | --- | --- |
| dataset_id | TEXT | 主键 |
| name | TEXT | 非空 |
| source_type | TEXT | 非空 |
| path_alias | TEXT | 非空 |
| sha256 | TEXT | 唯一、非空 |
| row_count | INTEGER | 可空 |
| start_time / end_time | TEXT | ISO 8601 |
| status | TEXT | 非空 |
| metadata_json | TEXT | 非敏感 JSON |
| created_at | TEXT | 非空 |

### 9.2 preprocess_runs

- preprocess_id 主键；
- dataset_id 外键；
- config_hash；
- output_path_alias；
- status；
- summary_json；
- started_at、completed_at。

### 9.3 model_runs

- run_id 主键；
- model_id 可空；
- preprocess_id；
- model_type；
- config_hash；
- device；
- status；
- best_epoch；
- metrics_json；
- artifact_path_alias；
- started_at、completed_at。

### 9.4 forecasts

- forecast_id 主键；
- dataset_id；
- model_id；
- forecast_start；
- request_hash；
- status；
- artifact_path_alias；
- latency_ms；
- created_at。

### 9.5 alerts

- alert_id 主键；
- forecast_id 可空；
- dataset_id；
- model_id 可空；
- alert_type；
- severity；
- start_time、end_time；
- status；
- evidence_json；
- note；
- created_at、updated_at。

### 9.6 optimization_scenarios

- scenario_id 主键；
- source_type、source_id；
- request_json；
- result_json；
- status；
- created_at。

### 9.7 reports

- report_id 主键；
- evidence_hash；
- generation_mode；
- provider_alias；
- model_alias；
- status；
- artifact_path_alias；
- diagnostics_json；
- created_at。

### 9.8 settings

只允许保存非敏感设置。API Key 和 Authorization 不得进入此表。

## 10. 数据库规则

- 开启外键；
- 写操作使用短事务；
- 所有时间存 ISO 8601 文本；
- JSON 字段先经 Pydantic 校验；
- SQLite 锁定时有限重试；
- 数据库迁移有版本表；
- 不直接删除被报告引用的数据和模型记录；
- 清理产物时先检查引用关系。

## 11. OpenAI 兼容接口契约

### 11.1 配置

| 环境变量 | 必需 | 说明 |
| --- | --- | --- |
| OPENAI_API_KEY | 启用 LLM 时是 | 密钥 |
| OPENAI_BASE_URL | 否 | 兼容服务地址；为空使用 SDK 默认 |
| OPENAI_MODEL | 启用 LLM 时是 | 模型名称 |
| OPENAI_API_STYLE | 否 | auto、chat_completions 或 responses，默认 auto |
| OPENAI_TIMEOUT_SECONDS | 否 | 默认 30 |
| OPENAI_MAX_RETRIES | 否 | 默认 1 |
| LLM_ENABLED | 否 | 默认 false，配置完整后开启 |
| LLM_SEND_RAW_SERIES | 否 | 固定默认 false；MVP 页面不建议开启 |

### 11.2 兼容能力探测

兼容层以 Chat Completions 作为第三方服务的最低兼容基线，因为“兼容 OpenAI 接口”不代表服务实现了所有 OpenAI 新接口。若服务明确支持 Responses 且当前 SDK 暴露对应客户端，则可以选择 Responses。对于直接使用官方 OpenAI API 的新项目，官方文档当前推荐 Responses，同时说明 Chat Completions 仍受支持。

连接测试应依次判断：

1. 客户端能否创建；
2. 基础地址能否访问；
3. 鉴权是否成功；
4. 模型是否存在；
5. 配置的接口风格是否受支持；auto 模式先做能力探测；
6. 是否支持结构化输出，以及所选接口对应的参数形式；
7. 响应字段能否被 SDK 正确解析。

实现应封装适配层，不让页面依赖具体 API 风格。Chat Completions 的结构化输出通常使用 response_format，Responses 的参数形状不同，官方迁移文档给出的结构化输出入口为 text.format，因此两种请求必须分别构造，不能只替换 URL。选择哪种接口以用户服务实测为准；未知第三方服务不应在未探测时默认发送 Responses 请求。

官方口径参考：

- [Migrate to the Responses API](https://developers.openai.com/api/docs/guides/migrate-to-responses)
- [Responses API reference](https://developers.openai.com/api/docs/api-reference/responses/create)
- [Chat Completions API reference](https://developers.openai.com/api/docs/api-reference/chat/create)

### 11.3 错误映射

| 类别 | 界面信息 | 是否重试 |
| --- | --- | --- |
| invalid_config | 配置不完整 | 否 |
| authentication | API Key 无效或无权限 | 否 |
| model_not_found | 模型名不可用 | 否 |
| rate_limit | 请求受限 | 最多一次延迟重试 |
| timeout | 服务超时 | 最多一次 |
| upstream_error | 上游服务错误 | 最多一次 |
| invalid_response | 返回格式不符合报告契约 | 一次修复请求 |
| content_rejected | 服务拒绝内容 | 否，回退模板 |
| unknown | 未知错误，查看脱敏诊断 | 否或一次 |

任何错误信息不得包含完整 Key 或 Authorization 头。

## 12. 错误码

| 前缀 | 模块 | 示例 |
| --- | --- | --- |
| DATA | 数据 | DATA_SCHEMA_MISSING_COLUMN |
| PREP | 预处理 | PREP_LONG_GAP_CONTEXT |
| MODEL | 模型 | MODEL_INCOMPATIBLE_SCHEMA |
| FCST | 预测 | FCST_INSUFFICIENT_HISTORY |
| ALERT | 预警 | ALERT_RULE_CONFIG_INVALID |
| OPT | 优化 | OPT_NO_FEASIBLE_ALLOCATION |
| LLM | 大模型 | LLM_AUTHENTICATION_FAILED |
| STORE | 存储 | STORE_DATABASE_LOCKED |
| EXPORT | 导出 | EXPORT_PATH_NOT_WRITABLE |

错误对象至少包含 code、user_message、technical_message、recoverable、suggested_action 和 request_id。technical_message 只进入诊断视图和日志。

## 13. 幂等与缓存

- 相同数据、配置和版本的预处理返回同一可复用产物；
- 相同 ForecastRequest 的 request_hash 可复用缓存；
- 相同 evidence_hash 和模板版本可复用报告；
- 更新预警状态不是幂等创建，必须按 alert_id 更新；
- API 重试不能生成多个可见重复报告记录。

## 14. 公共 REST 扩展

MVP 不实现 REST。若后续确有需求，可映射：

- POST /datasets/validate；
- POST /forecasts；
- GET /forecasts/{id}；
- GET /alerts；
- POST /optimization/scenarios；
- POST /reports。

增加 REST 必须重新评估鉴权、CORS、文件上传、并发、超时和部署工作量，不能为了形式在课程 MVP 中提前引入。

## 15. 契约验收

- Pydantic 对象能序列化和反序列化；
- 产物包含 schema_version 和来源 ID；
- 不兼容版本被拒绝；
- API Key 不出现在 SQLite、日志和导出；
- 预测、预警、情景和报告可追溯；
- 失败对象提供稳定错误码；
- 相同请求缓存行为可重复。

## 16. 变更记录

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| v0.1.0 | 2026-07-21 | 定义内部服务、领域对象、文件产物、SQLite 和 LLM 接口契约 |
