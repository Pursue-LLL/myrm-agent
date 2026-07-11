# core/infra/

## 架构概述

端口、CORS、限流、前端子进程启动等基础设施。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 包入口与导出 | — |
| `cors_validator.py` | 模块 | CORS 配置和验证 | ✅ |
| `frontend_launcher.py` | 模块 | Next.js standalone frontend launcher for WebUI mode. | ✅ |
| `idle_handlers.py` | 模块 | Server-side idle task handlers. | ✅ |
| `ingress.py` | 模块 | 公网 Ingress 单一解析入口；30s 内存缓存 + `invalidate_public_ingress_cache()`，避免 AuthMiddleware 每条 API 请求打 DB | ✅ |
| `ingress_requirement.py` | 模块 | 汇总已配置渠道与 Cron Webhook，判定是否需公网 Ingress；供 `/system/ingress-requirement` 与渠道 issues 补充。 | ✅ |
| `limiter.py` | 模块 | limiter 模块实现 | — |
| `server_globals.py` | 模块 | Server Global State Management | ✅ |
| `tls_config.py` | 模块 | Enterprise TLS configuration bridge (DB→env var sync for MYRM_TLS_STRICT). | ✅ |
| `ws_origin_guard.py` | 模块 | WebSocket Origin guard. | ✅ |
