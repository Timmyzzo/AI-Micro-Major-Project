# 11 启动与演示

## 启动

先在当前 PowerShell 配置 `LLM_ENABLED=true`、`OPENAI_API_KEY`、`OPENAI_MODEL` 和需要的 `OPENAI_BASE_URL`，然后执行：

~~~powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\start_powerinsight.ps1
~~~

修改大模型 Key、模型或 Base URL 后，使用 `-Restart` 重启当前项目实例并重新打开浏览器：

~~~powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\start_powerinsight.ps1 -Restart
~~~

脚本自动选择端口并打开默认浏览器。完整说明见 [系统使用指南](15-system-usage-guide.md)。

## 推荐演示流程

1. 首页确认四项核心功能状态，说明当前大模型型号，点击“测试 API 连接”；
2. 数据中心说明 UCI 数据来源、时间范围、记录规模和覆盖率；
3. 用电分析选择日期，展示 KPI、趋势、周期和分项用电；
4. 负荷预测选择时间和三个主要模型之一，展示 24 小时预测、90% 区间和双语指标；
5. 智能建议点击“生成智能建议”，展示大模型回复；
6. 监测预警作为补充，回放历史负荷并导出预警 CSV；
7. 系统设置快速展示 GPU、预测模型数量和大模型型号。

## 展示原则

- 不解释开发阶段编号和内部产物名称；
- 不展示哈希、模型运行 ID、缓存路径或配置指纹；
- 不在主流程中运行数据校验或模型训练；
- 页面指标以中文名称为主，保留常见英文缩写；
- 大模型测试和建议必须由用户点击触发，并显示成功或失败状态。
