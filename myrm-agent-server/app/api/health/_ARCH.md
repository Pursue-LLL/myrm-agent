# api/health/

## 架构概述

健康检查、就绪探针与性能基准 HTTP 层。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 包入口与导出 | — |
| `benchmark.py` | 模块 | Provides asynchronous performance benchmark execution and SSE streaming | ✅ |
| `browser.py` | 模块 | 浏览器运行时健康端点：`/browser` 健康、`/browser/doctor` 诊断（真实端口注入 relay 探测）、`/browser/orphans` GET/DELETE（统一 automation 扫描 + confirm 安全门 + failed 透传）、云/代理连通性测试 | ✅ |
| `diagnostic.py` | 模块 | Returns the current hardened diagnostic state of the agent engine. | ✅ |
| `memory.py` | 模块 | Memory diagnostics API. | ✅ |
| `liveness.py` | 模块 | Agent 全局存活状态 SSOT 端点（`GET /api/v1/health/liveness`），聚合 Agent 活跃会话、渠道健康、内存压力、`pendingOutboundCount`；返回 `draining` 状态当 gateway 正在排空 | ✅ |
| `router.py` | 路由 | HTTP 路由处理器（含 health/readiness；doctor 经 `health_snapshot` 采集、`health_alert_policy` fail-only SSE；挂载 browser 等子路由） | ✅ |
