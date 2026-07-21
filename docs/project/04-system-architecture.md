# 04 系统架构设计

## 1. 架构结论

项目采用“模块化单体 + 本地文件产物 + SQLite 元数据”的架构：

- 一个 Streamlit 进程承载页面和应用编排；
- 数据、模型、预警、优化和大模型逻辑放在独立 Python 模块；
- 页面只负责输入、展示和调用服务；
- 原始与处理后时序数据使用文件保存；
- SQLite 保存轻量元数据、运行记录、预警状态和报告索引；
- 外部仅依赖可选的 OpenAI 兼容 API。

该架构可以在单台游戏本上开发、训练和演示，避免前后端分离、微服务、Redis、消息队列等非必要工作。

## 2. 系统上下文

~~~mermaid
flowchart LR
    U["本地操作用户"] --> APP["PowerInsight Streamlit 应用"]
    CSV["内置或上传 CSV"] --> APP
    APP --> FS["本地数据、模型与报告文件"]
    APP --> DB["SQLite 元数据"]
    APP --> GPU["PyTorch / RTX 4060"]
    APP --> LLM["OpenAI 兼容 API，可选"]
~~~

系统不会连接真实电表或执行设备控制。历史回放是对 CSV 的时间推进模拟。

## 3. 逻辑分层

~~~mermaid
flowchart TB
    UI["展示层：Streamlit 页面、Plotly 图表、状态组件"]
    APP["应用层：用例编排、会话状态、导出、缓存"]
    DOMAIN["领域层：数据质量、特征、预测、预警、优化、报告"]
    INFRA["基础设施层：CSV/Parquet、SQLite、模型文件、OpenAI 客户端、日志"]
    UI --> APP
    APP --> DOMAIN
    DOMAIN --> INFRA
~~~

依赖方向必须向下。领域层不得依赖 Streamlit；这样可以在没有页面的情况下进行单元测试。

## 4. 模块划分

| 模块 | 职责 | 不负责 |
| --- | --- | --- |
| config | 合并默认值、配置文件、环境变量和会话配置 | 页面布局、业务计算 |
| data_catalog | 数据集登记、指纹、路径和 schema 版本 | 清洗算法 |
| data_validation | 字段、类型、时间、缺失、重复和范围检查 | 模型推理 |
| preprocessing | 解析、缺失处理、聚合、派生特征、时间切分 | 页面展示 |
| analytics | KPI、周期、分项、典型日和确定性摘要 | 自由文本生成 |
| forecasting | 模型加载、输入窗口、推理、区间、评估 | 数据上传 |
| alerting | 质量、规则、残差预警与等级 | 大模型判断等级 |
| optimization | 峰谷电价和负荷转移情景 | 真实控制 |
| llm_reporting | 证据组装、API 调用、结构校验和模板回退 | 计算预测与费用 |
| persistence | SQLite 和文件元数据读写 | 业务规则 |
| export | CSV、JSON、Markdown 和图片导出 | 修改原始数据 |
| ui | 页面、组件、交互和展示状态 | 复杂业务逻辑 |

## 5. 目标代码目录

以下是实现阶段的计划目录，不表示当前已经存在：

~~~text
AI-Micro-Major-Project/
├─ README.md
├─ CONTRIBUTING.md
├─ pyproject.toml
├─ requirements.txt
├─ requirements-gpu.txt
├─ .env.example
├─ configs/
│  ├─ default.yaml
│  ├─ demo.yaml
│  └─ model/
│     └─ patchtst_small.yaml
├─ app/
│  ├─ streamlit_app.py
│  ├─ pages/
│  ├─ components/
│  └─ assets/
├─ src/
│  └─ powerinsight/
│     ├─ config.py
│     ├─ schemas.py
│     ├─ data/
│     ├─ analytics/
│     ├─ models/
│     ├─ alerts/
│     ├─ optimization/
│     ├─ llm/
│     ├─ persistence/
│     └─ services/
├─ scripts/
│  ├─ validate_data.py
│  ├─ prepare_data.py
│  ├─ train_baselines.py
│  ├─ train_patchtst.py
│  ├─ evaluate.py
│  └─ prepare_demo.py
├─ data/
│  ├─ raw/
│  ├─ interim/
│  ├─ processed/
│  └─ manifests/
├─ models/
│  ├─ checkpoints/
│  ├─ scalers/
│  └─ registry/
├─ artifacts/
│  ├─ forecasts/
│  ├─ reports/
│  ├─ figures/
│  ├─ exports/
│  └─ demo/
├─ logs/
├─ tests/
│  ├─ unit/
│  ├─ integration/
│  ├─ data/
│  ├─ model/
│  └─ ui/
└─ docs/
   ├─ project/
   └─ 原始课程资料
~~~

原始 CSV 目前位于 docs。实现阶段可在 data/raw 中建立受控副本或配置引用，但不得移动或覆盖课程原文件而导致文档链接失效。

## 6. 核心数据流

~~~mermaid
flowchart LR
    RAW["原始 CSV"] --> CHECK["Schema 与质量校验"]
    CHECK --> CLEAN["时间解析与缺失策略"]
    CLEAN --> AGG["15 分钟聚合"]
    AGG --> FEAT["时间与派生特征"]
    FEAT --> SPLIT["按月份切分"]
    SPLIT --> TRAIN["训练与验证"]
    SPLIT --> ANALYZE["确定性分析"]
    TRAIN --> REG["模型注册"]
    REG --> PRED["预测与共形区间"]
    PRED --> ALERT["残差与规则预警"]
    ANALYZE --> OPT["优化情景"]
    ANALYZE --> EVID["证据包"]
    ALERT --> EVID
    OPT --> EVID
    PRED --> EVID
    EVID --> REPORT["大模型或模板报告"]
~~~

每个节点产生可追踪的输入版本、配置摘要、状态和输出路径。

## 7. 训练与演示分离

### 7.1 训练流程

1. 校验数据指纹和 schema；
2. 生成处理后数据与 manifest；
3. 训练朴素、Ridge、LSTM 和 PatchTST；
4. 在验证集选择参数与早停；
5. 在测试集运行最终评估；
6. 校准 90% 共形区间；
7. 保存模型、缩放器、配置、指标和模型卡；
8. 生成演示缓存。

训练不在 Streamlit 页面启动是更稳妥的默认方案。页面可显示训练说明和结果，但课程现场只做模型加载与推理。

### 7.2 演示流程

1. 启动应用；
2. 加载已处理数据和模型注册信息；
3. 加载或即时生成短时预测；
4. 使用缓存结果作为网络、GPU或时间兜底；
5. 大模型可按需调用，失败时使用模板。

## 8. 预测调用时序

~~~mermaid
sequenceDiagram
    actor User as 用户
    participant UI as 预测页面
    participant S as ForecastService
    participant D as DataService
    participant M as ModelRegistry
    participant C as Cache
    User->>UI: 选择预测起点和模型
    UI->>S: 创建预测请求
    S->>D: 获取并校验 672 点上下文
    S->>M: 加载模型、缩放器和配置
    S->>C: 查询同配置缓存
    alt 缓存有效
        C-->>S: 返回预测
    else 无缓存
        S->>S: 推理并反缩放
        S->>S: 应用共形校准
        S->>C: 保存预测和元数据
    end
    S-->>UI: 96 点预测、区间和运行信息
    UI-->>User: 图表、指标和导出
~~~

## 9. 大模型报告时序

~~~mermaid
sequenceDiagram
    actor User as 用户
    participant UI as 报告页面
    participant E as EvidenceBuilder
    participant L as LLMService
    participant V as ResponseValidator
    participant T as TemplateReporter
    User->>UI: 点击生成报告
    UI->>E: 选择数据、预测、预警和情景
    E-->>UI: 展示脱敏证据预览
    UI->>L: 用户确认后发送
    alt API 成功
        L-->>V: 结构化响应
        V-->>UI: 合法报告
    else API 失败或响应不合法
        L-->>T: 错误类别和证据
        T-->>UI: 本地模板报告
    end
    UI-->>User: 报告、证据和生成方式
~~~

## 10. 配置架构

配置优先级从低到高：

1. 代码内安全默认值；
2. configs/default.yaml；
3. configs/demo.yaml 或指定配置；
4. 环境变量；
5. 命令行参数；
6. 当前 Streamlit 会话设置。

API Key 只能来自环境变量或安全输入，不写入 YAML。每次训练和预测保存“解析后的非敏感配置快照”。

## 11. 存储架构

### 11.1 文件存储

- CSV/Parquet：原始、处理中间和聚合数据；
- safetensors 或 PyTorch 权重：模型；
- JSON/YAML：manifest、配置和指标；
- CSV：预测、预警和优化结果；
- Markdown/HTML：报告；
- PNG/SVG：课程报告图表。

### 11.2 SQLite

SQLite 只保存索引和小型记录：

- 数据集目录；
- 模型运行与模型注册；
- 预测运行；
- 预警和确认状态；
- 优化情景；
- 报告索引；
- 非敏感系统设置。

不把 26 万行原始时序重复写入 SQLite，避免不必要的数据库设计和性能成本。表契约见[接口与存储契约](07-interface-and-storage-contracts.md)。

## 12. 缓存策略

| 缓存 | Key | 失效条件 |
| --- | --- | --- |
| 数据读取 | 文件指纹、解析配置 | 文件或 schema 改变 |
| 处理数据 | dataset_id、处理配置版本 | 任一输入或规则改变 |
| 图表聚合 | dataset_id、时间范围、粒度、指标 | 选择或数据改变 |
| 模型对象 | model_id、设备 | 权重、配置或设备改变 |
| 预测 | model_id、dataset_id、起点、区间配置 | 任一参数改变 |
| 报告 | evidence_hash、模板版本、模型别名 | 证据或模板改变 |

缓存结果必须显示生成时间，不能把过期缓存伪装成即时结果。

## 13. 错误与降级

| 故障 | 降级行为 |
| --- | --- |
| CSV 不合法 | 保留问题报告，不进入预测 |
| 处理数据缺失 | 重新生成或返回修复提示 |
| CUDA 不可用 | 切 CPU 推理 |
| GPU 显存不足 | 减小批量；演示时加载缓存 |
| 模型不兼容 | 拒绝加载并显示契约差异 |
| SQLite 锁定 | 短暂重试，必要时只读显示 |
| LLM 未配置/超时/限流 | 模板报告 |
| 导出目录无权限 | 提示选择可写目录，不丢失页面结果 |
| 缓存损坏 | 删除单个缓存并重新计算，不影响原始数据 |

## 14. 观测性

实现阶段应有：

- 结构化本地日志；
- run_id、dataset_id、model_id、request_id；
- 步骤耗时；
- 缓存命中；
- GPU/CPU 设备；
- API 状态码类别和重试次数；
- 异常堆栈仅写诊断日志，界面显示简化错误。

日志必须过滤 API Key、Authorization 请求头、完整提示词和用户上传路径中的敏感信息。

## 15. 性能设计

- 预先生成 15 分钟和小时粒度 Parquet；
- 大范围图表先聚合或下采样；
- 模型对象按 model_id 与设备缓存；
- 单次推理只处理一个或有限批次窗口；
- 大模型按用户操作调用，不自动重复；
- 页面只加载当前页需要的数据；
- 训练与页面进程分离，避免界面阻塞。

## 16. 安全边界

1. 外部 API 只接收用户确认的证据包；
2. Key 不入数据库、日志、报告或缓存；
3. 上传文件不执行，不信任文件名；
4. 导出 CSV 对等号、加号、减号和 at 符号开头的文本进行公式注入处理；
5. 所有模型和规则输出均标注教学用途；
6. 大模型不能覆盖计算结果或预警等级。

## 17. 架构验收

- 页面模块可以被替换而不改变领域逻辑测试。
- 无 LLM、无 CUDA、无网络时系统仍可加载历史数据和缓存结果。
- 数据、模型、预测、预警和报告可通过 ID 关联。
- 原始 CSV 未被覆盖。
- 应用只需一个本地服务进程即可完成演示。

## 18. 变更记录

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| v0.1.0 | 2026-07-21 | 确立模块化 Streamlit 单体、文件产物、SQLite 元数据和降级架构 |
