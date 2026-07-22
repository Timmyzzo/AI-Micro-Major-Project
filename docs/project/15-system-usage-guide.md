# 15 系统使用指南

## 1. 最短启动方式

PowerInsight 是本地 Streamlit 应用。最短启动方式是在项目根目录双击 `start_powerinsight.bat`，脚本会调用 PowerShell 启动器并自动打开浏览器。

### 1.1 配置大模型 API

在准备启动系统的 PowerShell 窗口中设置：

~~~powershell
$env:LLM_ENABLED = "true"
$env:OPENAI_API_KEY = "你的API Key"
$env:OPENAI_MODEL = "你的模型名称"
$env:OPENAI_BASE_URL = "https://你的OpenAI兼容接口地址/v1"
~~~

OpenAI 兼容 Base URL 应以 `/v1` 结尾，不要填写到 `/chat/completions`。如果直接使用 OpenAI 官方接口，可以不设置 `OPENAI_BASE_URL`。不要把真实 Key 写入 YAML、README、截图或 Git 提交。

### 1.2 首次安装依赖

~~~powershell
cd D:\code\AI-Micro-Major-Project
uv sync --extra dev --frozen
~~~

### 1.3 启动系统

双击：

~~~text
start_powerinsight.bat
~~~

或者在 PowerShell 中执行：

~~~powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\start_powerinsight.ps1
~~~

脚本会自动选择 8501—8510 中的可用端口、启动系统并打开默认浏览器。浏览器没有自动出现时，根据 PowerShell 输出访问类似地址：

~~~text
http://127.0.0.1:8501
~~~

如果已经运行过系统，之后又修改了 API Key、模型名称或 Base URL，请使用：

~~~powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\start_powerinsight.ps1 -Restart
~~~

该命令只重启当前项目的 PowerInsight 进程，并重新打开浏览器，使新的环境变量生效。

## 2. 五分钟答辩展示顺序

1. 首页总览：查看数据、分析、预测和预警状态，确认大模型型号，点击“测试 API 连接”。
2. 数据中心与用电分析：说明 UCI 公开数据规模、时间范围、覆盖率和历史用电规律。
3. 负荷预测：选择预测时间与模型，展示未来 24 小时曲线、90% 区间和三个模型的固定测试指标。
4. 监测预警：选择时间与模型，点击“一键启动监测”，展示预测从 1/96 按 0.5 秒间隔持续推进。
5. 智能建议：点击“生成智能建议”，展示四部分长建议，并点击“一键导出建议（Markdown）”。

## 3. 首页总览

首页直接展示：

- 数据是否就绪；
- 用电分析是否可用；
- 负荷预测模型数量；
- 监测预警是否可用；
- 数据时间范围、分析粒度和覆盖率；
- 大模型 API 状态；
- 当前大模型型号。

点击“测试 API 连接”后，系统会向当前模型发送一条简短测试消息。成功时显示模型回复和响应耗时，失败时显示连接失败状态。

## 4. 数据中心

当前系统使用：

- 数据集：Individual Household Electric Power Consumption；
- 来源：UCI Machine Learning Repository；
- 对象：法国 Sceaux 一户家庭的分钟级用电记录；
- 字段：总有功功率、电压、电流和三项分表电量。

来源链接：<https://archive.ics.uci.edu/dataset/235/individual+household+electric+power+consumption>

页面展示原始记录数、当前系统使用的时间范围、15 分钟分析数据点、覆盖率和数据示例。

如果分析数据尚未准备，点击一次“准备分析数据”即可。已有分析数据时无需执行任何数据操作。

## 5. 用电分析

1. 选择开始日期和结束日期；
2. 查看累计有功电量、平均有功功率、峰值和覆盖率；
3. 查看历史负荷趋势；
4. 查看每小时和每星期的用电规律；
5. 比较工作日与周末；
6. 查看厨房、洗衣房、热水器/空调和未分项电量。

如果所选范围存在缺失区段，页面会用一条简短提示说明，趋势图保留断点。

## 6. 负荷预测

页面只展示三个主要模型：

- 昨日同刻基线：使用前一天相同时间的负荷作为参照；
- LSTM 神经网络：循环神经网络负荷预测模型；
- PatchTST 深度模型：基于时间片段和 Transformer 的预测模型。

操作方式：

1. 选择预测时间；
2. 选择模型；
3. 点击“开始预测”；
4. 查看未来 24 小时预测曲线；
5. 查看 90% 预测区间；
6. 查看预测指标；
7. 需要时展开“查看模型训练过程”，查看 LSTM 与 PatchTST 每轮训练损失和验证 MAE；
8. 下载预测 CSV。

指标含义：

- MAE 平均绝对误差：平均每个时间点偏差多少 kW，越低越好；
- RMSE 均方根误差：对较大误差更敏感，越低越好；
- WAPE 加权绝对百分比误差：相对总负荷的误差比例，越低越好；
- sMAPE 对称平均绝对百分比误差：对称百分比误差，越低越好；
- R² 决定系数：越接近 1 越好；
- 90% 区间覆盖率：实际值进入预测区间的比例；
- 平均区间宽度：预测不确定性范围。

负荷预测是回归任务，不使用分类任务的 Accuracy。

## 7. 监测预警

1. 选择回放时间；
2. 选择预测模型；
3. 点击“一键启动监测”；
4. 系统从第一个预测点开始，每 0.5 秒自动增加一个点，96 点约 48 秒播放完成；
5. 播放过程中查看真实负荷、预测负荷、当前进度和已出现预警；
6. 播放结束后使用滑块回看任意时间点；
7. 按类型和等级筛选预警，并导出预警 CSV。

## 8. 智能建议

页面显示有效数据覆盖率、累计电量、平均负荷和峰值负荷。

点击“生成智能建议”后，系统调用当前配置的大模型，并根据这些用电摘要生成内容较完整的中文建议。建议按现状判断、峰值管理、日常执行和持续观察四部分组织，可生成约 1000 字内容。成功时显示模型回复和“一键导出建议（Markdown）”按钮，导出文件名为 `powerinsight_advice.md`；失败时直接显示调用错误。

最终验收已通过项目真实调用确认 `mode=api`、`diagnostic=None`，并成功生成和导出建议。

## 9. 系统设置

系统设置页用于查看：

- Python 和 PyTorch 版本；
- GPU 与 CUDA 状态；
- 用电数据状态；
- 三个展示模型是否可用；
- 大模型 API 状态；
- 当前大模型型号。

## 10. 重新训练模型

当前仓库已经包含可用的数据与模型结果，正常展示不需要重新训练。

需要重建时执行：

~~~powershell
.\.venv\Scripts\python.exe scripts\validate_data.py --config configs\default.yaml
.\.venv\Scripts\python.exe scripts\prepare_data.py --config configs\default.yaml
.\.venv\Scripts\python.exe scripts\train_m4.py --config configs\default.yaml --device auto
~~~

训练过程会保存每轮训练损失、验证误差、最佳轮次、模型权重和测试指标。系统页面只展示昨日同刻基线、LSTM 和 PatchTST 三个主要模型。

## 11. 常见问题

### 大模型状态显示“等待配置”

确认启动 PowerShell 中已经设置 `OPENAI_API_KEY` 和 `OPENAI_MODEL`，然后使用启动脚本的 `-Restart` 参数重新启动系统。

### API 测试失败

检查 Base URL、模型名称、账户余额和网络连接。更改环境变量后使用 `-Restart` 重新启动应用。

### 数据中心显示“分析数据尚未准备”

点击“准备分析数据”。

### 负荷预测显示模型未准备

运行 `scripts\train_m4.py` 后重新启动系统。

### 端口被占用

继续使用推荐启动脚本，它会自动选择可用端口。
