# 11 启动与演示

## 启动

~~~powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\start_powerinsight.ps1
~~~

或：

~~~powershell
.\.venv\Scripts\python.exe -m streamlit run app\streamlit_app.py
~~~

## 推荐演示流程

1. 首页查看数据、模型和环境状态；
2. 数据中心展示固定课程 CSV、缺失证据和 15 分钟产物；
3. 用电分析展示 KPI、趋势和周期；
4. 负荷预测展示模型卡、预测区间和真实指标；
5. 监测预警回放一个 96 点片段并导出 CSV；
6. 智能建议展示本地模板；如已配置 Key，主动调用一次 API；
7. 系统设置说明本地存储和安全边界。

## 降级

- 无网络或无 Key：本地模板建议可用；
- API 超时或失败：回退本地模板；
- CUDA 不可用：CPU 推理；
- 权重缺失：兼容朴素默认模型仍可推理；
- 全部模型不兼容：历史分析仍可用，预测明确阻断；
- 数据产物缺失：引导用户在数据中心处理固定内置数据。

## 不演示

上传数据、字段映射、优化调度、完整智能报告、HTML、REST、云部署或设备控制。
