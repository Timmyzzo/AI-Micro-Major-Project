# 智电洞察（PowerInsight）

面向《电力人工智能综合实训》的本地 Streamlit 项目，使用课程固定家庭用电 CSV，完成数据治理、历史分析、24 小时负荷预测、预测区间、历史回放和确定性预警，并保留一个可选的大模型 API 简短建议入口。

## 当前状态

项目已完成主要功能，简化后的功能进度超过 80%。

| 模块 | 状态 |
| --- | --- |
| 工程、环境和七页导航 | 已完成并验证 |
| 固定内置数据校验与预处理 | 已完成并验证 |
| 历史用电分析 | 已完成并验证 |
| 基线、LSTM、PatchTST、共形区间 | 已完成并验证 |
| 24 小时预测与离线缓存 | 已完成并验证 |
| 历史回放与三类预警 | 已完成并验证 |
| 本地模板建议 | 已实现 |
| 可选大模型 API 简短建议 | 已实现代码与 mock 测试；真实调用取决于用户配置 |
| 最终课程截图、Word/PDF 报告 | 已完成并逐页验证 |

项目不再建设任意 CSV 上传、字段映射、多数据集管理、优化调度平台、完整智能报告系统、HTML 报告或 REST API。
当前完整自动化回归为 128 项 pytest，Ruff、格式、mypy、pip check、pre-commit 和七页 AppTest 均通过。

## 七个页面

1. 首页总览
2. 数据中心
3. 用电分析
4. 负荷预测
5. 监测预警
6. 智能建议
7. 系统设置

数据中心只处理仓库内的课程固定数据集，不接受用户上传文件。

## 已验证结果

- 数据身份：`ds_household_power_c79e3e19`
- 处理身份：`prep_c79e3e19_cb65036717cf`
- 原始记录：260,640 行
- 问号缺失：3,771 行
- 最长缺失段：3,723 分钟
- 15 分钟点数：17,376
- 历史分析有效点：17,127
- 覆盖率：98.567%
- 累计有功电量：4,988.285 kWh
- M4 正式运行：`m4_20260721_104201`
- 默认模型：前一日同刻
- 默认模型测试 MAE：0.6463 kW
- PatchTST 测试 MAE：0.6622 kW
- PatchTST 相对 Last Value MAE 改善：9.62%
- 预警验收：质量 4 条、规则 6 条、残差 13 条，共 23 条
- 七页浏览器验收：1920×1080 全部通过；等效 125% 缩放无横向溢出
- 课程报告：15 页 A4 Word/PDF，目录、正文页码、7 张最终截图和 7 个表格已验证

复杂模型没有在测试集上超过前一日同刻基线；项目保留这一负结果，不修改测试集或夸大结论。
最终验收环境未安全配置大模型 API，因此真实 API 调用按规则跳过；本地模板和 mock 回退测试均通过。

## 启动

~~~powershell
uv sync --extra dev --frozen
.\.venv\Scripts\python.exe scripts\check_environment.py
.\.venv\Scripts\python.exe -m streamlit run app\streamlit_app.py
~~~

也可以运行：

~~~powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\start_powerinsight.ps1
~~~

## 固定数据处理

~~~powershell
.\.venv\Scripts\python.exe scripts\validate_data.py --config configs\default.yaml
.\.venv\Scripts\python.exe scripts\prepare_data.py --config configs\default.yaml
~~~

原始 CSV 只读；处理结果写入被 `.gitignore` 保护的 `data/` 和 `artifacts/`。

## 可选大模型建议

没有 API Key 时，智能建议页显示本地模板。需要调用 API 时，在环境变量中配置：

~~~dotenv
LLM_ENABLED=true
OPENAI_API_KEY=your-key
OPENAI_MODEL=your-model
OPENAI_BASE_URL=
OPENAI_TIMEOUT_SECONDS=30
~~~

实现只调用一次 Chat Completions，将数据覆盖率、累计电量、平均/峰值负荷和默认模型测试 MAE 等聚合摘要发送给 API。不会发送原始 CSV、完整时序、API Key、预测权重或本地路径。API 失败时回退本地模板。

## 范围边界

- 不接入真实电表或控制设备。
- 不提供电气安全诊断。
- 不提供真实调度或费用优化。
- 不支持上传数据和字段映射。
- 不让大模型参与数据清洗、预测数值或预警分级。
- 不把单户课程数据结论推广到其他家庭。

## 文档

项目基线见 [docs/project/README.md](docs/project/README.md)。最终课程截图位于
`docs/课程提交报告/screenshots/`，Word/PDF 位于 `docs/课程提交报告/`。
提交前只需填写封面个人信息、按实际修改小组分工，并进行现场演示复核。

## Git 规则

每个独立功能完成后运行测试、同步文档、提交并推送。API Key、模型权重、运行缓存、数据库和本地报告不得提交。
