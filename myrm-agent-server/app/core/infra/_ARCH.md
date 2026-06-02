
# app/core/infra 模块架构

基础设施工具层。提供 CORS 验证、前端启动器、空闲处理、限流、端口管理和全局状态等运行时基础能力。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `cors_validator.py` | 辅助 | CORS origins 配置解析与验证 | ⚠️ 待补 |
| `ingress.py` | 核心 | Public Ingress Resolver Core. 统一解析 SaaS/单机公网地址（供 Middleware/API/Webhook 校验复用） | ✅ |
| `tunnel/` | 核心 | Cloudflare Quick Tunnel 进程生命周期（仅本地/WebUI 部署） | ✅ |
| `ws_origin_guard.py` | 辅助 | WebSocket Origin 验证守卫。在 ws.accept() 前校验 Origin header 防止跨站 WebSocket 劫持 (CSWSH)。复用 cors_origins 配置，无 Origin 放行、不匹配则 close(4003) | ✅ |
| `frontend_launcher.py` | 辅助 | Next.js standalone 前端子进程启动器（WebUI 模式），包含端口探测与健康检查 | ⚠️ 待补 |
| `idle_handlers.py` | 辅助 | Harness 层空闲任务的 Server 端处理器。注册 wiki_maintenance 和 _context_compact_impl（空闲上下文压缩）handler | ✅ |
| `limiter.py` | 辅助 | 应用层限流器（暴力破解防护） | ⚠️ 待补 |
| `server_globals.py` | 辅助 | 全局共享实例状态管理 | ⚠️ 待补 |

## 子模块索引

| 子模块 | 职责 |
|--------|------|
| `tunnel/` | Cloudflare Quick Tunnel 进程生命周期，详见 [tunnel/_ARCH.md](tunnel/_ARCH.md) |
| `health/` | 业务层健康检查实现。Qdrant/SQLite/Browser资源的健康检查与自动恢复。 |
