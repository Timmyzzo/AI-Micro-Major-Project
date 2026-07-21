# 04 系统架构

## 形态

单进程 Streamlit 应用，业务逻辑位于 `src/powerinsight`，页面位于 `app/pages`。不增加前端框架、REST 服务、任务队列或远程数据库。

## 数据流

~~~text
固定课程 CSV
  -> 校验与预处理
  -> Parquet + manifest
  -> 历史分析
  -> 模型训练/注册
  -> 冻结预测与缓存
  -> 回放与确定性预警
  -> 本地模板建议
  -> 用户可选的一次 Chat Completions 调用
~~~

## 模块

- `data`：固定数据校验、预处理和 manifest；
- `analytics`：纯确定性分析；
- `forecasting`：窗口、模型、指标、共形和注册；
- `alerts`：质量、规则和残差预警；
- `services/advice_service.py`：聚合摘要、本地模板和一次 API 调用；
- `persistence`：保留现有轻量元数据，时序仍存文件。

## 删除的架构

不建设上传适配器、优化服务、完整报告服务、Responses 适配层、业务 REST API、alerts/optimization/reports 新持久化流程或云端组件。
