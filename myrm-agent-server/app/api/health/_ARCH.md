# api/health/

## 架构概述

健康检查与就绪探针 HTTP 层。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 包入口与导出 | — |
| `browser.py` | 模块 | 浏览器运行时健康端点：`/browser` 健康（池健康读取失败降级为 `unhealthy` 并记 warning 日志）、`/browser/doctor` 诊断（把 server 自有的 `extension_relay` 检查作为 `run_doctor` 的 `extra_checks` 传入，relay 行计入报告与 summary）、`/browser/orphans` GET/DELETE（统一 automation 扫描 + confirm 安全门 + 联动沙箱清理与空间释放透出（预览与清理共用 harness 默认沙箱年龄阈值，预览数即清理数）+ failed 透传；失败时先 `logger.exception` 记录根因再返回通用 500）、云/代理连通性测试 | ✅ |
| `memory.py` | 模块 | Memory diagnostics API. | ✅ |
| `liveness.py` | 模块 | Agent 全局存活状态 SSOT 端点（`GET /api/v1/health/liveness`），聚合 Agent 活跃会话、渠道健康、内存压力、`pendingOutboundCount`、`gatewayRuntime` 零载荷 vitals；gateway 异常时 `state=degraded`；`metrics_enabled` 时刷新 Prometheus `myrm_gateway_*` gauges | ✅ |
| `router.py` | 路由 | HTTP 路由处理器（含 health/readiness、`/health/info` 系统配置与数据驻留 `data_region` 透出；doctor 经 `health_snapshot` 采集、`health_alert_policy` fail-only SSE；挂载 browser 等子路由；`POST /health/database/safe-purge` 会话清空，有会话运行中返回 409） | ✅ |
| `pressure.py` | 模块 | 用户态资源压力端点（`GET /api/v1/health/pressure`）：内存 level 直读 harness monitor、data_dir 磁盘 85/95 诚实阈值、失败 unknown 降级 | ✅ |
| `update_status.py` | 模块 | Stack Update 真相端点（`GET /api/v1/health/update-status`）：版本比对主信号、rev-list 备援、FIXED/OTHER 与 is_security 安全分组、prebuilt 启动摘要、cloud 诚实未知；默认 1 小时缓存，支持 force=true 实时穿透探针与并发 Singleflight 任务复用锁 | ✅ |
