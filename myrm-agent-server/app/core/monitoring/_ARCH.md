# app/core/monitoring 模块架构


---

## 架构概述

业务层监控入口：Prometheus 指标初始化、OpenTelemetry 追踪初始化、DB Pool 指标注册。
框架层不感知 sandbox_id，业务层在导出时可统一添加。

---

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 核心 | 监控入口（Prometheus 指标、OpenTelemetry 追踪初始化、DB Pool 指标注册） | ✅ |
| `prometheus_setup.py` | 核心 | FastAPI HTTP 指标初始化（prometheus_fastapi_instrumentator） | ✅ |
| `gateway_vitals_metrics.py` | 核心 | Gateway runtime Prometheus gauges（`myrm_gateway_event_loop_lag_ms` / `_process_rss_mb` / `_active_asyncio_tasks` / `_health_status_code`）；由 liveness 探针刷新 | ✅ |
