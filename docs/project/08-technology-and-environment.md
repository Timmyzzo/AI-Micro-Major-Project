# 08 技术与环境

## 技术栈

- Python 3.11.14
- Streamlit
- pandas / NumPy / PyArrow
- scikit-learn
- PyTorch / Transformers
- Plotly
- SQLite
- OpenAI Python SDK
- pytest / Ruff / mypy / pre-commit

## 安装与启动

~~~powershell
uv sync --extra dev --frozen
.\.venv\Scripts\python.exe scripts\check_environment.py
.\.venv\Scripts\python.exe -m streamlit run app\streamlit_app.py
~~~

CUDA 不可用时允许 CPU 推理。Streamlit 页面不训练模型。

## API 环境变量

~~~dotenv
LLM_ENABLED=false
OPENAI_API_KEY=
OPENAI_BASE_URL=
OPENAI_MODEL=
OPENAI_TIMEOUT_SECONDS=30
~~~

YAML 不允许保存 Key。未配置 API 时应用正常启动并显示本地建议。

## 不采用

Docker、云部署、Redis、任务队列、远程数据库、Node 前端、REST 服务和多提供商自动路由均不属于项目范围。
