# app/core/monitoring 模块架构


---

## 架构概述

业务层监控指标导出器。将 harness 框架层的 metrics 数据导出到业务层监控系统（Prometheus、日志等）。
框架层不感知 sandbox_id，业务层在导出时可统一添加。

---

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 核心 | 监控入口（Prometheus 指标、OpenTelemetry 追踪初始化、DB Pool 指标注册） | ✅ |
| `llm_metrics_exporter.py` | 核心 | LLM 重试指标导出（成功率、延迟、重试次数） | ✅ |
| `slack_thread_metrics_exporter.py` | 核心 | Slack 线程指标导出 | ✅ |

---

## 依赖关系

- `myrm_agent_harness`：`EmptyRetryMetrics`、`ChatLiteLLM` 等框架层 metrics 数据
