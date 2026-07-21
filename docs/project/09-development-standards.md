# 09 开发规范

## 代码

- 业务逻辑放在 `src/powerinsight`，页面只做交互和展示；
- 公共函数有类型标注和简短 docstring；
- 不为已删除范围保留新抽象；
- 不在 Streamlit 页面训练模型；
- 不把计划值写成实测结果。

## 安全

- 原始 CSV 只读；
- API Key 只来自环境变量或会话配置；
- Key 不进入源码、YAML、SQLite、日志、截图和导出；
- API 只接收聚合摘要；
- CSV 导出防止公式注入；
- 建议必须声明课程演示边界。

## 质量门禁

~~~powershell
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\ruff.exe format --check .
.\.venv\Scripts\python.exe -m mypy src
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\pre-commit.exe run --all-files
git diff --check
~~~

## Git

每个独立结果完成后测试、同步文档、提交并推送。不得提交 Key、权重、数据库、缓存、日志或最终个人信息报告。
