# 智电洞察（PowerInsight）

面向《电力人工智能综合实训》的电力数据智能分析与可视化系统。当前版本使用 UCI `Individual Household Electric Power Consumption` 公开数据，提供数据概览、用电分析、24 小时负荷预测、监测预警和外部大模型智能建议。

## 当前功能

| 功能 | 状态 |
| --- | --- |
| 七页 Streamlit 界面 | 已完成 |
| UCI 家庭用电数据处理 | 已完成 |
| 历史趋势、周期与分项分析 | 已完成 |
| 昨日同刻、LSTM、PatchTST 三模型展示 | 已完成 |
| 24 小时预测与 90% 预测区间 | 已完成 |
| 历史回放与预警 | 已完成；一次点击后每 0.5 秒自动推进 1 个预测点 |
| 外部大模型智能建议 | 已完成真实项目调用、长建议生成、状态反馈与 Markdown 一键导出 |
| LSTM/PatchTST 逐轮训练历史 | 已保存；负荷预测页可折叠查看，课程报告包含完整训练损失、验证 MAE 和最佳轮次 |
| 课程交付材料 | 两份最终报告（DOCX/PDF）与 12 页答辩 PPT 已完成 |

## 快速启动

最方便的启动方式是在项目根目录双击 `start_powerinsight.bat`。脚本会调用 PowerShell 启动器，复用健康实例或在 8501—8510 中选择可用端口，并自动打开浏览器。

首次使用外部大模型前，在 PowerShell 中配置连接；OpenAI 兼容 Base URL 应以 `/v1` 结尾：

~~~powershell
$env:LLM_ENABLED = "true"
$env:OPENAI_API_KEY = "你的API Key"
$env:OPENAI_MODEL = "你的模型名称"
$env:OPENAI_BASE_URL = "https://你的OpenAI兼容接口地址/v1"
~~~

安装依赖并启动：

~~~powershell
cd D:\code\AI-Micro-Major-Project
uv sync --extra dev --frozen
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\start_powerinsight.ps1
~~~

也可以直接双击根目录的 `start_powerinsight.bat`。

如果系统已经运行，之后又修改了 API Key、模型或 Base URL，使用下面的命令让新配置立即生效并重新打开浏览器：

~~~powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\start_powerinsight.ps1 -Restart
~~~

## 七个页面

1. 首页总览：查看核心功能状态、大模型型号并测试 API 连接。
2. 数据中心：查看 UCI 数据来源、时间范围、数据规模和示例。
3. 用电分析：查看电量、负荷趋势、周期规律和分项用电。
4. 负荷预测：选择时间和模型，生成未来 24 小时负荷预测。
5. 监测预警：点击一次后按 0.5 秒间隔逐点播放 96 步预测与预警，并支持筛选和 CSV 导出。
6. 智能建议：调用外部大模型生成较完整的四部分中文建议，并一键导出 Markdown。
7. 系统设置：查看计算环境、数据、预测模型和大模型连接信息。

## 数据来源

- 数据集：Individual Household Electric Power Consumption；
- 来源：UCI Machine Learning Repository；
- 来源链接：<https://archive.ics.uci.edu/dataset/235/individual+household+electric+power+consumption>；
- 当前系统使用范围：2007 年 1 月至 6 月；
- 原始记录：260,640 行；
- 15 分钟分析数据点：17,376；
- 有效数据覆盖率：98.567%。

当前界面不支持上传任意 CSV。更换其他公开电力数据时，需要重新适配字段、单位、时间粒度和数据切分，并重新训练模型。

## 预测模型与指标

页面保留三个主要模型：

- 昨日同刻基线；
- LSTM 神经网络；
- PatchTST 深度模型。

负荷预测属于回归任务，使用以下指标：

- MAE 平均绝对误差；
- RMSE 均方根误差；
- WAPE 加权绝对百分比误差；
- sMAPE 对称平均绝对百分比误差；
- R² 决定系数；
- 90% 区间覆盖率和平均区间宽度。

当前测试结果中，昨日同刻基线 MAE 为 0.6463 kW，PatchTST MAE 为 0.6622 kW。项目保留这一真实比较结果，不因深度模型复杂度而夸大效果。

## 重新准备数据与训练

正常展示不需要重新训练。需要重建时执行：

~~~powershell
.\.venv\Scripts\python.exe scripts\validate_data.py --config configs\default.yaml
.\.venv\Scripts\python.exe scripts\prepare_data.py --config configs\default.yaml
.\.venv\Scripts\python.exe scripts\train_m4.py --config configs\default.yaml --device auto
~~~

## 文档

- [项目文档目录](docs/project/README.md)
- [系统使用指南](docs/project/15-system-usage-guide.md)
- [答辩展示界面优化与验收清单](docs/project/16-defense-ui-optimization.md)
- [小组项目报告最终版（DOCX）](docs/课程提交报告/《电力人工智能综合实训》小组项目报告-最终版.docx)，同时提供 PDF；
- [实验报告最终版（DOCX）](docs/课程提交报告/《电力人工智能综合实训》实验报告-最终版.docx)，同时提供 PDF；
- [PowerInsight 答辩展示最终版（PPTX）](docs/课程提交报告/《电力人工智能综合实训》PowerInsight答辩展示-最终版.pptx)。

小组项目报告共 16 个物理页面，实验报告共 14 个物理页面；两份 PDF 均已逐页渲染检查。答辩 PPT 共 12 页，已完成逐页渲染和溢出检测。七页截图均来自最终代码，其中监测页实测从 1/96 自动推进到 12/96。

提交前只需将报告封面中的学院、班级、学号、指导助教和小组姓名占位符替换为实际信息；小组贡献比例已按 40% / 25% / 25% / 10% 写入。API Key、运行缓存和本地日志不得提交。
