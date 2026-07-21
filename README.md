# 电力数据智能分析与可视化系统

> 项目展示名：智电洞察（PowerInsight）
> 基础实验：实验 6《家庭用电数据集的探索》
> 当前阶段：M2 数据闭环与 M2.5 全局前端体验重构已实现并验证；M3 分析和后续模型业务尚未开始
> 文档基线版本：v0.4.0（2026-07-21）
> GitHub 仓库：[Timmyzzo/AI-Micro-Major-Project](https://github.com/Timmyzzo/AI-Micro-Major-Project)

本项目面向《电力人工智能综合实训》，基于家庭分钟级用电数据，设计一个集数据接入、数据质量检查、用电监测、负荷预测、异常预警、用能分析、优化模拟和大模型解释于一体的本地可视化系统。项目以“技术有新意、结果可验证、工作量可控制、现场展示稳定”为核心原则。

项目计划采用轻量级 PatchTST 时序 Transformer 预测未来 24 小时家庭负荷，使用按预测步长校准的共形预测区间表达不确定性，结合预测残差和数据规则识别异常，再通过兼容 OpenAI 接口的大模型，把确定性的统计结果、预测结果和优化模拟结果转换为有依据的中文分析报告。大模型不会直接预测数值，也不会控制真实电力设备。

## 1. 当前仓库状态

当前仓库已完成可启动工程骨架、M2 数据闭环和独立的 M2.5 前端体验重构：内置 CSV 可被真实校验，短/长缺失按规则处理，数据聚合为 15 分钟并按固定月份切分，Parquet 与 manifest 可重复生成，SQLite 登记轻量元数据，八个 Streamlit 页面使用集中式设计 token、统一状态语言和可访问性降级。模型业务仍处于计划状态。

| 项目 | 当前状态 |
| --- | --- |
| 需求、功能、架构、数据、模型设计 | 已形成文档基线 |
| 开发规范、环境方案、测试与验收方案 | 已形成文档基线 |
| Python 与依赖 | Python 3.11.14 项目环境已验证；`pyproject.toml` + `uv.lock` 为权威依赖入口 |
| 应用界面 | Streamlit 八页导航、集中式主题、共享布局/状态组件、Material Symbols 导航和非敏感诊断已实现 |
| SQLite | schema v1 已复用；实际登记 1 个数据集和 1 个已完成预处理运行，不保存原始或聚合时序 |
| 自动化质量 | Ruff、格式、mypy、pip check 和 76 项 pytest 已通过；最终 pre-commit 结果见测试文档 |
| 数据预处理产物 | 已在本地生成分钟 Parquet、15 分钟 Parquet 和 manifest；均为 `.gitignore` 保护的可再生产物，不提交 Git |
| 模型训练与评估结果 | 未执行 |
| 系统截图与课程报告结果章节 | 待实现后补充 |
| Git 仓库 | [Timmyzzo/AI-Micro-Major-Project](https://github.com/Timmyzzo/AI-Micro-Major-Project)，默认分支 main |

不得把文档中的“计划值”“预估值”描述成已经实测的系统结果。后续实现和训练产生的真实版本号、耗时、显存、指标和截图，应回填到相应文档及课程报告。

### M2.5 前端体验重构

本阶段只重构展示层，没有改变 M2 数据契约、SQLite schema、处理规则或八页顺序，也没有引入新依赖、前端框架和第二个服务进程。

- `app/theme.py` 集中管理颜色、材质、排版、间距、圆角、阴影、密度与交互时序 token。
- `app/components/layout.py` 提供页面身份、状态面板、事实列表和 sidebar 应用身份。
- 首页把真实 M2 数据状态作为主层级，同时明确模型仍“尚未训练”。
- 数据中心保留完整 SHA-256、主动校验、主动预处理、缺失证据、切分、manifest 和小型预览。
- 用电分析、负荷预测、监测预警、优化决策和智能报告均为诚实计划状态，不展示伪造图表、指标或连接结果。
- 系统设置按运行环境、存储职责、配置来源和安全边界分组；SQLite 仍只存元数据，不存时序。
- 按钮在按下时即时反馈；动效仅用于 hover、press 和状态变化，不使用 bounce、循环背景或不可中断的复杂动画。
- 支持 `prefers-reduced-motion`、`prefers-reduced-transparency`、`prefers-contrast` 和清晰的 `:focus-visible`。

真实无头 Chrome 已逐页检查 1920×1080，并抽查 1366×768、浅色/深色、sidebar 折叠以及 125%/150% 缩放等效 CSS 视口。Chrome 可自动模拟 reduced motion；reduced transparency 和 increased contrast 的 CSS 合约已自动测试，但仍需在支持相应系统媒体查询的桌面环境中人工切换复核。

### 已验证的本地启动方式

~~~powershell
uv sync --extra dev --frozen
.\.venv\Scripts\python.exe scripts\check_environment.py
.\.venv\Scripts\python.exe -m streamlit run app\streamlit_app.py
~~~

首次建立环境时，`uv` 会按 `.python-version` 获取 CPython 3.11.14。应用默认禁用 LLM，不需要 API Key 即可启动；完整数据校验和预处理只由数据中心按钮或命令行脚本显式触发，不会在页面刷新时自动执行，也不会训练模型或调用外部 API。

### M2 数据命令

~~~powershell
.\.venv\Scripts\python.exe scripts\validate_data.py --config configs\default.yaml
.\.venv\Scripts\python.exe scripts\prepare_data.py --config configs\default.yaml
~~~

当前内置数据的稳定身份为 `ds_household_power_c79e3e19`，默认处理身份为 `prep_c79e3e19_cb65036717cf`。相同源文件和相同配置安全重跑时保持相同 ID 和配置指纹。

## 2. 已有材料

| 文件 | 用途 |
| --- | --- |
| [实验 6 原始说明](docs/实验6——家庭用电数据集的探索.md) | 基础实验内容和数据来源说明 |
| [家庭用电 CSV](docs/household_power_consumption.csv) | 项目内置演示数据 |
| [实验报告模板](docs/课程提交报告/《电力人工智能综合实训》实验报告模板.doc) | 基础实验报告格式参考 |
| [小组项目报告模板](docs/课程提交报告/《电力人工智能综合实训》报告模板.doc) | 最终课程项目报告格式依据 |
| [项目文档中心](docs/project/README.md) | 全部设计文档的统一入口 |

`docs/课程提交报告`（课程提交报告）这个文件夹在项目未完成的情况下无需读取。

经 M2 程序化校验，CSV 包含 260,640 条分钟记录，时间范围为 2007-01-01 00:00:00 至 2007-06-30 23:59:00；共有 3,771 行测量值缺失，占 1.4468%，分为 13 段，其中最长连续缺失段为 3,723 分钟。默认规则实际插值 48 行短缺失并保留 3,723 行长缺失，生成 17,376 个 15 分钟点，固定切分为训练 11,520、验证 2,976、测试 2,880。数据字段、单位、清洗和切分规则见[数据规格与治理](docs/project/05-data-specification.md)。

## 3. 项目核心能力

系统 MVP 计划提供以下六类能力：

1. 数据采集与治理：内置 CSV、用户上传 CSV、字段校验、缺失统计、时间连续性检查和数据质量报告。
2. 监测与可视化：关键指标卡、负荷曲线、分项用电构成、峰谷时段、周期规律和模拟实时回放。
3. 智能预测：使用历史 7 天的 15 分钟序列，预测未来 24 小时共 96 个时间点，并展示 90% 预测区间。
4. 异常监测与预警：识别缺失、越界、负荷突增及预测残差异常，提供分级、证据、筛选和导出。
5. 优化与决策支持：通过峰谷电价和可转移负荷参数进行“如果……会怎样”的削峰与费用模拟，不执行真实控制。
6. 大模型分析报告：把结构化证据转换为中文摘要、风险解释和节能建议，API 不可用时自动退回模板报告。

## 4. 技术路线

| 层次 | 计划技术 | 选择原因 |
| --- | --- | --- |
| 展示层 | Streamlit、Plotly | Python 单栈、开发量小、适合课程现场演示 |
| 数据层 | pandas、NumPy、SQLite | 数据量适中，生态成熟，SQLite 仅保存元数据 |
| 预测层 | PyTorch、Hugging Face Transformers、PatchTST | 具有前沿时序 Transformer 特征，能在 RTX 4060 游戏本上训练 |
| 基线模型 | 季节朴素、Ridge、LSTM | 确认复杂模型相对传统方法是否真正有效 |
| 不确定性 | 分步 Split Conformal Prediction | 实现成本低、可解释、可验证覆盖率 |
| 预警 | 数据质量规则、预测残差、稳健阈值 | 将异常结论绑定到明确证据 |
| 决策支持 | 峰谷分析、可转移负荷情景模拟 | 避免在无控制动作和回报数据时伪造强化学习效果 |
| 大模型 | OpenAI Python SDK 的兼容接口模式 | 支持用户自有 base URL、模型名和 API Key |
| 质量工具 | pytest、Ruff、mypy、pre-commit | 保持可测试、可复现和可维护 |

完整选型和版本策略见[技术栈与环境配置](docs/project/08-technology-and-environment.md)。

## 5. 系统页面与目标能力

| 页面 | 展示重点 |
| --- | --- |
| 首页总览 | 数据范围、当前负荷、峰值、用电量、异常数、未来峰值 |
| 数据中心 | 导入、字段映射、质量检查、缺失区间、预处理摘要 |
| 用电分析 | 趋势、日历热力图、小时与星期规律、分项构成、相关性 |
| 负荷预测 | 基线与 PatchTST 对比、未来 24 小时、预测区间、指标 |
| 监测预警 | 模拟回放、异常时间线、等级、触发规则、处置状态 |
| 优化决策 | 峰谷电价、负荷转移情景、峰值与费用变化、建议 |
| 智能报告 | 一键生成有证据的大模型报告，并支持 Markdown 导出 |
| 系统设置 | 模型、设备、API、阈值、隐私和诊断设置 |

当前只有首页、数据中心和系统设置具备与 M1/M2 相称的真实状态展示；其余五页已完成 M2.5 计划态体验，但表中业务能力仍需在 M3 至 M5 实现。

具体页面字段、交互、状态和视觉规范见[功能与界面规格](docs/project/03-feature-and-ui-specification.md)。

## 6. 最小闭环

系统必须形成以下可演示闭环：

~~~text
导入数据
  → 校验并展示数据质量
  → 查看历史规律
  → 加载已训练模型并预测未来 24 小时
  → 根据预测与观测生成预警
  → 模拟峰谷负荷调整
  → 由大模型汇总证据并生成报告
  → 导出预测、预警或报告
~~~

大模型只是最后的解释层。即使 API 断网或余额不足，前面的数据分析、预测、预警和优化模拟仍须可用。

## 7. 文档导航

建议按以下顺序阅读：

1. [项目立项与范围](docs/project/01-project-charter.md)
2. [需求规格说明书](docs/project/02-requirements-specification.md)
3. [功能与界面规格](docs/project/03-feature-and-ui-specification.md)
4. [系统架构设计](docs/project/04-system-architecture.md)
5. [数据规格与治理](docs/project/05-data-specification.md)
6. [模型与智能分析设计](docs/project/06-model-and-intelligence-design.md)
7. [接口与存储契约](docs/project/07-interface-and-storage-contracts.md)
8. [技术栈与环境配置](docs/project/08-technology-and-environment.md)
9. [开发规范](docs/project/09-development-standards.md)
10. [测试与验收方案](docs/project/10-test-and-acceptance.md)
11. [部署、运维与演示手册](docs/project/11-deployment-operations-demo.md)
12. [计划、分工与风险](docs/project/12-plan-risk-and-collaboration.md)
13. [课程报告与 AI 使用说明](docs/project/13-course-report-and-ai-disclosure.md)
14. [术语、决策记录与待确认项](docs/project/14-glossary-decisions-and-open-items.md)

完整文档地图、适用对象和维护规则见[项目文档中心](docs/project/README.md)。

## 8. 硬件与运行目标

目标开发机为 Windows 游戏本，NVIDIA RTX 4060 Laptop GPU，建议至少 16 GB 内存和 10 GB 可用磁盘。计划通过以下方式控制训练资源：

- 将分钟数据聚合为 15 分钟数据。
- 使用 7 天上下文和 24 小时预测长度。
- PatchTST 默认隐藏维度 64、3 层编码器、4 个注意力头。
- 使用混合精度、早停和小批量训练。
- 保留 CPU 推理与缓存预测作为演示兜底。

显存占用和训练时长目前均为设计预估，必须在实现阶段实测后记录，不能在报告中伪装成已验证结果。

## 9. 版本控制与提交要求

- 远程仓库：[https://github.com/Timmyzzo/AI-Micro-Major-Project](https://github.com/Timmyzzo/AI-Micro-Major-Project)。
- main 分支必须保持可启动、可测试或至少与当前项目阶段一致。
- 后续每完成一个可独立验收的功能，都要先运行对应检查、同步文档，再立即创建一次语义清晰的 Git 提交并推送远程。
- 不把多个已经完成的功能长期堆积在一个大提交中，也不提交未验证的半成品作为“功能完成”。
- 环境、数据、模型和大模型相关提交必须检查 API Key、缓存、权重和可再生产物是否被正确忽略。

详细规则见[项目协作与贡献指南](CONTRIBUTING.md)和[开发规范](docs/project/09-development-standards.md)。

## 10. 数据来源与致谢

项目子集来自 UCI Individual Household Electric Power Consumption 数据集的 2007 年 1 月至 6 月记录，原作者为 Georges Hebrail 与 Alice Berard，数据集 DOI 为 [10.24432/C58K54](https://doi.org/10.24432/C58K54)。课程材料同时给出了对应的 [Kaggle 页面](https://www.kaggle.com/datasets/thedevastator/240000-household-electricity-consumption-records)。
