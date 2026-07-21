# 08 技术栈与环境配置

## 1. 当前状态声明

截至 2026-07-21，M1 至 M4 已在目标 Windows 电脑上实现并验证：项目使用 uv 管理的 CPython 3.11.14 和 `.venv`，依赖已锁定，CUDA 版 PyTorch、数据闭环、历史分析、六模型训练评估、共形区间、离线缓存和 Streamlit 推理页均可运行。预警、优化和真实 OpenAI 兼容 API 仍未实现。

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

## 3. 已安装并验证的版本

以下是 Python 3.11.14 环境在 2026-07-21 实际安装、导入并锁定的直接依赖。`pyproject.toml` 声明精确直接依赖，`uv.lock` 是完整权威锁文件；`requirements.txt` 和 `requirements-dev.txt` 由锁文件导出，不单独维护版本。

| 包或工具 | 已验证版本 |
| --- | --- |
| Python | 3.11.14 |
| uv | 0.9.26 |
| pip / setuptools / wheel | 26.1.2 / 83.0.0 / 0.47.0 |
| torch | 2.13.0+cu130 |
| transformers | 5.14.1 |
| pandas | 3.0.3 |
| NumPy | 2.4.6（Python 3.11 可用的当前兼容版本；2.5.1 要求 Python 3.12） |
| PyArrow | 24.0.0 |
| scikit-learn | 1.9.0 |
| SciPy | 1.17.1 |
| Streamlit | 1.59.2 |
| Plotly | 6.9.0 |
| Pydantic / pydantic-settings | 2.13.4 / 2.14.2 |
| OpenAI Python SDK | 2.46.0（仅导入验证，未连接真实服务） |
| PyYAML / joblib | 6.0.3 / 1.5.3 |
| pytest | 9.1.1 |
| Ruff / mypy / pre-commit | 0.15.22 / 2.3.0 / 4.6.0 |
| types-PyYAML | 6.0.12.20260518 |

PyTorch 通过官方 `https://download.pytorch.org/whl/cu130` 显式索引锁定，未混装 CPU wheel 或其他 CUDA 来源。Prophet、pytest-cov 和与 M1 无关的服务依赖均未安装；当前测试没有设置覆盖率阈值，因此暂不引入 pytest-cov。

## 4. 目标硬件

### 4.1 已实测设备

- 操作系统：Windows 11 专业版 64 位，版本 10.0.26200；
- CPU：12th Gen Intel Core i7-12650H，10 核 16 线程；
- 内存：16,456,184 KiB 可见内存，约 15.7 GiB；
- GPU：NVIDIA GeForce RTX 4060 Laptop GPU，compute capability 8.9；
- 显存：`nvidia-smi` 报告 8,188 MiB；PyTorch 报告 8,585,216,000 字节；
- NVIDIA 驱动：610.47，驱动侧 CUDA UMD 13.3；
- PyTorch CUDA runtime：13.0；
- 环境检查时 D 盘可用空间约 115 GiB。

### 4.2 可降级

- 无 GPU：允许 CPU 推理和小样本冒烟训练；
- 只有 8 GB 内存：减少 DataLoader worker 和缓存；
- 无网络：除依赖首次安装和 LLM 外，核心演示使用本地产物。

## 5. 已建立的环境配置文件

当前已创建并验证：

| 文件 | 内容 |
| --- | --- |
| pyproject.toml | 项目元数据、工具配置和核心依赖 |
| requirements.txt | 当前 Windows 运行依赖的锁定导出，包含已验证 CUDA torch |
| pyproject.toml 中的 uv source | 固定 PyTorch 官方 CUDA 13.0 wheel 来源 |
| requirements-dev.txt | pytest、Ruff、mypy、pre-commit |
| uv.lock | 完整权威锁文件 |
| .env.example | 不含真实密钥的变量模板 |
| configs/default.yaml | 安全默认配置 |
| configs/demo.yaml | 现场演示配置 |
| configs/model/patchtst_small.yaml | 模型默认参数 |

不单独维护 `requirements-gpu.txt`：GPU 来源已由 `pyproject.toml` 的显式 uv index 和 `uv.lock` 唯一确定，避免再维护一套可能冲突的 torch 版本。`.venv`、缓存、数据库和日志不提交。

## 6. Windows 环境建立

### 6.1 前置检查

~~~powershell
py -0p
uv --version
uv python list 3.11
nvidia-smi
~~~

实测结果：

- Windows `py` 启动器最初只有 Python 3.13 和 3.14，没有 Python 3.11；
- 本机已有 uv 0.9.26，可提供项目隔离的 CPython 3.11.14；
- `nvidia-smi` 正常显示 RTX 4060 Laptop GPU、驱动 610.47 和 8,188 MiB 显存；
- 项目盘空间充足，项目路径可读写。

不要求单独安装完整 CUDA Toolkit。PyTorch 官方 CUDA wheel 自带所需运行库；是否需要 Toolkit 取决于后续是否编译自定义 CUDA 扩展，本项目不计划编译。

### 6.2 创建虚拟环境

~~~powershell
Set-Location D:\code\AI-Micro-Major-Project
uv python install 3.11.14
uv venv --python 3.11.14 --seed .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip setuptools wheel
~~~

该方式没有修改系统默认 Python，也不要求永久改变 PowerShell 执行策略。`.python-version` 固定 3.11.14；激活虚拟环境不是运行命令的前提，文档统一使用显式解释器路径。

### 6.3 安装 PyTorch

官方索引在本次安装时提供 `torch 2.13.0+cu130` 的 Python 3.11 Windows wheel。本机驱动侧 CUDA 13.3 能运行 CUDA 13.0 wheel，因此项目通过 `pyproject.toml` 固定以下来源：

~~~toml
[[tool.uv.index]]
name = "pytorch-cu130"
url = "https://download.pytorch.org/whl/cu130"
explicit = true

[tool.uv.sources]
torch = { index = "pytorch-cu130" }
~~~

安装由 `uv sync` 按锁文件完成，不再单独执行第二套 pip torch 命令。

### 6.4 安装项目依赖

权威安装命令：

~~~powershell
uv sync --extra dev --frozen
~~~

如需只使用 pip 的导出入口，可使用 `requirements.txt` 或 `requirements-dev.txt`；这两个文件必须由 `uv export` 重新生成，不能手工改变版本。

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

本次实测：`torch.cuda.is_available()` 为 `True`，设备为 `NVIDIA GeForce RTX 4060 Laptop GPU`，CUDA runtime 为 13.0；矩阵运算和诊断脚本中的 CUDA 张量校验均通过。

### 6.6 验证应用依赖

~~~powershell
.\.venv\Scripts\python.exe scripts\check_environment.py
~~~

诊断脚本实际完成 30 项检查并以退出码 0 结束，覆盖关键依赖、项目包、CUDA、SQLite、原始 CSV 指纹、目录可写性和无密钥 LLM 状态。

## 7. 非 GPU 环境

当前 Windows 锁文件面向目标 RTX 4060 电脑，但应用的 `device=cpu` 降级路径可以在同一 CUDA wheel 环境中使用，不要求每次切换 wheel。若以后要为完全无 NVIDIA 环境建立独立安装包，应从 PyTorch 当时的官方 CPU 索引重新生成并验证单独的锁文件，不得在当前 `.venv` 中直接覆盖 torch 来源。

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
  unmetered_negative_tolerance_wh: 1.0e-9
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

## 11. 当前命令与后续计划

M1 已验证命令：

~~~powershell
uv sync --extra dev --frozen
.\.venv\Scripts\python.exe scripts\init_db.py
.\.venv\Scripts\python.exe scripts\check_environment.py
.\.venv\Scripts\python.exe -m streamlit run app\streamlit_app.py
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m mypy src
.\.venv\Scripts\python.exe -m pytest
~~~

M2 已创建并验证：

~~~powershell
.\.venv\Scripts\python.exe scripts\validate_data.py --config configs\default.yaml
.\.venv\Scripts\python.exe scripts\prepare_data.py --config configs\default.yaml
~~~

M4 已创建并验证：

~~~powershell
.\.venv\Scripts\python.exe scripts\train_m4.py `
  --config configs\default.yaml `
  --model-config configs\model\patchtst_small.yaml `
  --device cuda --train-stride 4 --eval-stride 96 --max-epochs 12
.\.venv\Scripts\python.exe scripts\accept_m4.py
~~~

模型训练仍与 Streamlit 页面分离。权重、缩放器和预测缓存不提交 Git；模型卡、指标、共形分位数和配置指纹位于 `models/registry/`。

## 12. 训练配置档位

| 档位 | 用途 | batch | d_model | 层数 | epoch |
| --- | --- | ---: | ---: | ---: | ---: |
| smoke | 环境与流水线测试 | 8 | 32 | 1 | 2 |
| laptop | RTX 4060 默认 | 32 | 64 | 3 | 30 上限 |
| low_memory | OOM 回退 | 8 或 16 | 48 | 2 | 20 |
| cpu | 无 GPU 冒烟 | 4 | 32 | 1 | 2 |

训练时长和显存必须实测，不能直接把档位目标写进结果章节。

## 13. 环境验证清单

- [x] Python 3.11.14 符合 `.python-version` 和锁文件；
- [x] `.venv` 可用，命令不依赖激活状态；
- [x] 所有当前直接依赖导入成功；
- [x] `nvidia-smi` 正常；
- [x] PyTorch 检测到 CUDA；
- [x] GPU 张量测试成功；
- [x] 内置 CSV 指纹一致；
- [x] 必要项目目录可写；
- [x] SQLite schema v1 可重复创建和读写；
- [x] Streamlit 无头健康检查返回 200/ok，测试后端口已释放；
- [x] Plotly 可导入；业务图表尚未实现；
- [x] LLM 正确禁用，无 API Key 仍可启动；真实兼容连接尚未测试；
- [x] 假密钥脱敏测试通过，提交前秘密扫描未发现真实 Key。

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

M1 已保存或记录：

- Python 3.11.14、uv 0.9.26 和 `uv.lock`；
- Windows、CPU、内存、NVIDIA 驱动、GPU 和显存摘要；
- torch 2.13.0+cu130 与 CUDA runtime 13.0；
- 原始数据 SHA-256；
- 当前启动、诊断和质量命令；
- Streamlit 健康检查、依赖检查和自动测试结果。

M4 已归档模型文件 SHA-256、配置指纹、训练时间、峰值模型分配显存、验证/测试指标、区间结果、推理延迟和保存/加载一致性。正式运行中 Ridge 训练 0.090 秒（CPU）；LSTM 3.425 秒、111.64 MiB；PatchTST 11.120 秒、65.57 MiB。专用 8502 浏览器验收结束后端口已释放，原 8501 项目进程未被结束。

## 18. 变更记录

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| v0.1.0 | 2026-07-21 | 建立技术栈、建议版本、Windows/GPU 配置、变量和故障排查方案 |
| v0.2.0 | 2026-07-21 | 回填 Python 3.11.14、锁定依赖、CUDA 13.0、RTX 4060 和 M1 环境验收结果 |
| v0.3.0 | 2026-07-21 | 回填 M2 数据脚本、处理配置和完整 CSV 验收状态 |
| v0.4.0 | 2026-07-21 | 回填 M4 正式训练命令、GPU/CPU 实测、模型产物和浏览器验收 |
