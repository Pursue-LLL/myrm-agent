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
