# core/infra/

## 架构概述

端口、CORS、限流、前端子进程启动等基础设施。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 包入口与导出 | — |
| `background_task.py` | 模块 | 长期存活 asyncio 后台任务的「启动 + 失败观测」：`spawn_observed_task`（起任务并挂 done callback；被模块全局持有的任务即使崩溃也永不触发 asyncio 的 "never retrieved" 报告，只能靠回调取回异常记 ERROR；取消是正常关闭路径，不算失败） | ✅ |
| `cors_validator.py` | 模块 | CORS 配置和验证 | ✅ |
| `frontend_launcher.py` | 模块 | Next.js standalone 前端启动器（环境检测、端口协调、毒性环境变量清洗、进程生命周期、崩溃重启） | ✅ |
| `idle_handlers.py` | 模块 | Server-side idle task handlers: 上下文压缩实现（`register_all_idle_handlers`）。 | ✅ |
| `ingress.py` | 模块 | 公网 Ingress 单一解析入口；30s 内存缓存 + `invalidate_public_ingress_cache()`，避免 AuthMiddleware 每条 API 请求打 DB；`resolve_share_url_base(fallback)` 供 chat/artifact 分享链接组装公网 base（无 ingress 降级 fallback） | ✅ |
| `ingress_requirement.py` | 模块 | 汇总已配置渠道与 Cron Webhook，判定是否需公网 Ingress；供 `/system/ingress-requirement` 与渠道 issues 补充。 | ✅ |
| `limiter.py` | 模块 | limiter 模块实现 | — |
| `tls_config.py` | 模块 | Enterprise TLS configuration bridge (DB→env var sync for MYRM_TLS_STRICT). | ✅ |
| `ws_origin_guard.py` | 模块 | WebSocket Origin guard. | ✅ |
