# 08 技术栈与环境配置

## 1. 当前状态声明

截至 2026-07-21，项目尚未创建虚拟环境、依赖文件或业务代码，也没有运行 GPU 检查和训练。本文档是实施方案。任何“兼容”“耗时”“显存”结论都应在实现阶段用目标电脑实测后回填。

## 2. 技术选型总表

| 类别 | 技术 | 用途 | 选择理由 |
| --- | --- | --- | --- |
| 语言 | Python 3.11 | 全项目 | PyTorch 和数据生态成熟，Windows 兼容性好 |
| UI | Streamlit | 本地多页面应用 | 单栈、开发量低、演示方便 |
| 图表 | Plotly | 交互式可视化 | 支持缩放、悬停和导出 |
| 数据 | pandas、NumPy、PyArrow | 读取、处理、Parquet | 当前 26 万行规模足够 |
| 传统模型 | scikit-learn | Ridge、缩放、指标 | 成熟且易复现 |
| 深度学习 | PyTorch | 训练和推理 | RTX 4060 CUDA 支持 |
| 时序模型 | Hugging Face Transformers PatchTST | 主预测模型 | 前沿且减少自定义实现 |
| 优化 | NumPy，扩展可用 SciPy | 负荷转移情景 | 可解释、工作量小 |
| 数据契约 | Pydantic | 配置和对象校验 | 防止接口漂移 |
| 大模型 | OpenAI Python SDK | 兼容接口调用 | 支持 base URL 和模型配置 |
| 元数据 | SQLite | 运行和预警记录 | 无需独立数据库 |
| 配置 | YAML、pydantic-settings | 默认值和环境变量 | 集中、可验证 |
| 测试 | pytest | 单元和集成测试 | Python 标准选择 |
| 质量 | Ruff、mypy、pre-commit | 格式、静态检查 | 自动化门禁 |
| 可选跟踪 | 本地 JSON/CSV，必要时 MLflow | 实验记录 | MVP 优先轻量本地记录 |

MVP 不引入 React/Vue、FastAPI、PostgreSQL、Redis、Kafka、Kubernetes 和云服务。

## 3. 建议版本基线

以下版本用于形成第一套可复现环境，当前尚未安装或验证。实现时若因驱动或包兼容性调整，必须更新锁文件和本文档。

| 包 | 建议基线 |
| --- | --- |
| Python | 3.11.x |
| torch | 2.5.1 |
| transformers | 4.46.x |
| pandas | 2.2.x |
| numpy | 1.26.x |
| pyarrow | 18.x |
| scikit-learn | 1.5.x |
| scipy | 1.14.x |
| streamlit | 1.40.x |
| plotly | 5.24.x |
| pydantic | 2.9.x |
| pydantic-settings | 2.6.x |
| openai | 首次集成时选择支持目标接口的稳定版并锁定；第三方兼容服务以连接测试为准 |
| PyYAML | 6.0.x |
| joblib | 1.4.x |
| pytest | 8.3.x |
| ruff | 0.7.x |
| mypy | 1.13.x |

选择较稳定的固定基线比盲目追新更适合课程项目。安装后应生成 requirements-lock.txt 或使用 uv.lock，最终报告记录实际版本。

## 4. 目标硬件

### 4.1 推荐

- Windows 10/11 64 位；
- NVIDIA RTX 4060 Laptop GPU；
- 8 GB 级显存，以 nvidia-smi 实际值为准；
- 16 GB 或更多内存；
- 4 核或更多 CPU；
- 至少 10 GB 可用磁盘；
- 1920×1080 显示或投屏。

### 4.2 可降级

- 无 GPU：允许 CPU 推理和小样本冒烟训练；
- 只有 8 GB 内存：减少 DataLoader worker 和缓存；
- 无网络：除依赖首次安装和 LLM 外，核心演示使用本地产物。

## 5. 环境配置文件计划

实现阶段应创建：

| 文件 | 内容 |
| --- | --- |
| pyproject.toml | 项目元数据、工具配置和核心依赖 |
| requirements.txt | 应用和 CPU 通用依赖 |
| requirements-gpu.txt | GPU 额外说明或固定 torch 来源 |
| requirements-dev.txt | pytest、Ruff、mypy、pre-commit |
| requirements-lock.txt 或 uv.lock | 完整锁定版本 |
| .env.example | 不含真实密钥的变量模板 |
| configs/default.yaml | 安全默认配置 |
| configs/demo.yaml | 现场演示配置 |
| configs/model/patchtst_small.yaml | 模型默认参数 |

当前这些文件尚不存在，文档中的命令需在实现阶段创建依赖文件后执行。

## 6. Windows 环境建立

### 6.1 前置检查

~~~powershell
py --version
py -0p
nvidia-smi
~~~

应确认：

- 可用 Python 3.11；
- nvidia-smi 能显示 RTX 4060；
- NVIDIA 驱动正常；
- 当前磁盘空间足够；
- 项目路径可读写。

不要求单独安装完整 CUDA Toolkit。PyTorch 官方 CUDA wheel 自带所需运行库；是否需要 Toolkit 取决于后续是否编译自定义 CUDA 扩展，本项目不计划编译。

### 6.2 创建虚拟环境

~~~powershell
Set-Location D:\code\AI-Micro-Major-Project
py -3.11 -m venv .venv
Set-ExecutionPolicy -Scope Process Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip setuptools wheel
~~~

### 6.3 安装 PyTorch

应以 PyTorch 官方安装选择器给出的、与实际驱动兼容的命令为准。计划基线可选择 CUDA 12.4 wheel。示意命令：

~~~powershell
python -m pip install torch==2.5.1 --index-url https://download.pytorch.org/whl/cu124
~~~

如果该组合在实际安装时不可用，应选择官方仍支持的 CUDA wheel，并在锁文件记录，不要同时混装多个 torch 来源。

### 6.4 安装项目依赖

实现阶段依赖文件存在后：

~~~powershell
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt
~~~

### 6.5 验证 GPU

~~~powershell
python -c "import torch; print('torch=', torch.__version__); print('cuda=', torch.cuda.is_available()); print('runtime=', torch.version.cuda); print('device=', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU')"
~~~

验收：

- torch 可导入；
- torch.cuda.is_available() 为 True；
- 设备名称与实际 GPU 一致；
- 能创建一个小张量并完成 CUDA 运算；
- 记录 torch、CUDA runtime 和驱动版本。

### 6.6 验证应用依赖

~~~powershell
python -c "import pandas, sklearn, streamlit, plotly, transformers, openai, pydantic; print('IMPORT_OK')"
~~~

## 7. 非 GPU 环境

CPU 环境可以安装普通 torch wheel：

~~~powershell
python -m pip install torch==2.5.1
~~~

CPU 用于：

- 数据校验；
- 图表和分析；
- 基线模型；
- 单窗口预测；
- 测试；
- 大模型报告。

正式 PatchTST 训练优先使用 GPU，但应用不能把 CUDA 作为启动硬依赖。

## 8. 环境变量

计划的 .env.example：

~~~text
APP_ENV=development
APP_LOG_LEVEL=INFO
APP_DATA_DIR=./data
APP_ARTIFACT_DIR=./artifacts
APP_DATABASE_PATH=./artifacts/powerinsight.db

DEVICE=auto
MODEL_ID=
MODEL_CACHE_SIZE=2

LLM_ENABLED=false
OPENAI_API_KEY=
OPENAI_BASE_URL=
OPENAI_MODEL=
OPENAI_API_STYLE=auto
OPENAI_TIMEOUT_SECONDS=30
OPENAI_MAX_RETRIES=1

STREAMLIT_SERVER_PORT=8501
STREAMLIT_BROWSER_GATHER_USAGE_STATS=false
~~~

规则：

- .env 不提交；
- .env.example 只含空值或假值；
- Key 不写 YAML；
- 界面只显示 Key 是否已配置和末尾最多 4 位，最好完全不回显；
- 环境变量加载失败时 LLM 默认关闭。

## 9. 默认数据配置

计划 configs/default.yaml 的文档化内容：

~~~yaml
data:
  builtin_path: docs/household_power_consumption.csv
  day_first: true
  raw_cadence: 1min
  target_cadence: 15min
  short_gap_max_minutes: 60
  bucket_min_valid_ratio: 0.8
  train_end: 2007-04-30T23:59:59
  validation_end: 2007-05-31T23:59:59
  test_end: 2007-06-30T23:59:59

forecast:
  context_length: 672
  prediction_length: 96
  interval_level: 0.9

ui:
  language: zh-CN
  default_theme: dark
  max_chart_points: 10000
~~~

这是配置契约示例，不是当前仓库中的实际文件。

## 10. 模型配置

计划 configs/model/patchtst_small.yaml：

~~~yaml
model:
  type: patchtst
  num_input_channels: 1
  context_length: 672
  prediction_length: 96
  patch_length: 16
  patch_stride: 8
  d_model: 64
  num_attention_heads: 4
  num_hidden_layers: 3
  ffn_dim: 128
  dropout: 0.1

training:
  seed: 42
  batch_size: 32
  max_epochs: 30
  learning_rate: 0.0001
  weight_decay: 0.0001
  gradient_clip: 1.0
  early_stopping_patience: 5
  mixed_precision: true
~~~

## 11. 计划命令

实现阶段应统一提供以下命令或等价脚本：

~~~powershell
python scripts/validate_data.py --config configs/default.yaml
python scripts/prepare_data.py --config configs/default.yaml
python scripts/train_baselines.py --config configs/default.yaml
python scripts/train_patchtst.py --config configs/default.yaml --model-config configs/model/patchtst_small.yaml
python scripts/evaluate.py --run-id <run_id>
python scripts/prepare_demo.py --model-id <model_id>
streamlit run app/streamlit_app.py
~~~

尖括号内容需要替换为真实 ID。当前阶段不要执行，因为对应脚本尚未创建。

## 12. 训练配置档位

| 档位 | 用途 | batch | d_model | 层数 | epoch |
| --- | --- | ---: | ---: | ---: | ---: |
| smoke | 环境与流水线测试 | 8 | 32 | 1 | 2 |
| laptop | RTX 4060 默认 | 32 | 64 | 3 | 30 上限 |
| low_memory | OOM 回退 | 8 或 16 | 48 | 2 | 20 |
| cpu | 无 GPU 冒烟 | 4 | 32 | 1 | 2 |

训练时长和显存必须实测，不能直接把档位目标写进结果章节。

## 13. 环境验证清单

- [ ] Python 版本符合锁文件；
- [ ] 虚拟环境已激活；
- [ ] 所有依赖导入成功；
- [ ] nvidia-smi 正常；
- [ ] PyTorch 检测到 CUDA；
- [ ] GPU 张量测试成功；
- [ ] 内置 CSV 指纹一致；
- [ ] 项目目录可写；
- [ ] SQLite 可创建和读写；
- [ ] Streamlit 能启动；
- [ ] Plotly 图能显示；
- [ ] OpenAI 兼容连接测试通过或 LLM 正确禁用；
- [ ] API Key 未出现在 Git 状态和日志。

## 14. 开发、测试和演示环境

| 环境 | 目的 | 特点 |
| --- | --- | --- |
| development | 日常开发 | 详细日志、热重载、可用小数据 |
| test | 自动测试 | 临时目录、固定种子、禁用真实 LLM |
| demo | 课程演示 | 内置数据、默认模型、缓存结果、较少日志 |

demo 环境不应自动训练，也不应在启动时自动调用外部 API。

## 15. 常见问题

### 15.1 PowerShell 禁止激活脚本

只对当前进程临时放开：

~~~powershell
Set-ExecutionPolicy -Scope Process Bypass
~~~

不建议为了项目永久降低系统执行策略。

### 15.2 torch.cuda.is_available() 为 False

检查：

1. nvidia-smi 是否正常；
2. 是否安装了 CPU wheel；
3. torch 来源是否正确；
4. 虚拟环境是否混用；
5. 驱动是否支持 wheel 的 CUDA runtime；
6. 重启终端后再次验证。

### 15.3 CUDA Out of Memory

依次尝试：

1. 关闭占用 GPU 的游戏、浏览器加速和其他程序；
2. batch size 32 → 16 → 8；
3. d_model 64 → 48 → 32；
4. 层数 3 → 2；
5. 启用混合精度；
6. 减少 DataLoader 预取；
7. 使用缓存预测完成演示。

不要通过删除测试数据或缩短预测长度来隐瞒资源问题，除非同步更新需求。

### 15.4 中文路径或编码问题

- 源码和 Markdown 使用 UTF-8；
- CSV 按明确编码读取；
- 内部路径使用 pathlib；
- 时间和字段内部使用英文稳定名；
- 不依赖终端当前代码页解析数据。

### 15.5 Streamlit 端口被占用

~~~powershell
streamlit run app/streamlit_app.py --server.port 8502
~~~

### 15.6 OpenAI 兼容服务失败

检查 base URL 是否包含正确版本路径、模型名、Key、代理、超时和服务支持的接口类型。失败时应用应使用本地模板，而不是阻止启动。

### 15.7 Transformers 与模型配置不兼容

- 核对锁文件；
- 检查 PatchTST 类和配置字段；
- 不在演示前临时升级；
- 模型权重与依赖版本一起归档；
- 运行兼容性测试后再替换环境。

## 16. 依赖升级规则

- 课程演示前 72 小时冻结依赖；
- 只为安全、阻断缺陷或明确功能需要升级；
- 升级后运行完整测试和模型加载测试；
- 已训练权重若受影响，重新评估；
- 更新锁文件、环境文档和模型卡；
- 不在演示当天升级 GPU 驱动或核心依赖。

## 17. 环境归档

项目完成时保存：

- Python 版本；
- pip freeze 或锁文件；
- nvidia-smi 摘要；
- torch、CUDA runtime、GPU；
- 操作系统版本；
- 数据指纹；
- 模型文件指纹；
- 启动命令；
- 真实训练时间、峰值显存和推理延迟。

## 18. 变更记录

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| v0.1.0 | 2026-07-21 | 建立技术栈、建议版本、Windows/GPU 配置、变量和故障排查方案 |
