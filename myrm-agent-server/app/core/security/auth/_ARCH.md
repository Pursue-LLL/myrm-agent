# core/security/auth 模块架构

---

## 架构概述

单租户 HTTP/WebSocket 认证辅助：公开路径规则（按路径 + 方法）+ 共享 identity 解析。HTTP 在 `auth.py`，WS 在 `ws_auth.py`。远程暴露路径支持 mobile pair token（HTTP header / query + WS query）；scoped control token 解析为 `ResolvedIdentity.pair_bound_chat_id` 供 handler 绑定 chat_id。Sandbox 模式下 CP 反代流量优先经 `cp_proxy.py` HMAC 验签，再 fallback API Key / 回环。

---

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `public_paths.py` | ✅ 核心 | 无需 API Key 的路径规则 `is_public_path(path, method)`：任意方法开放的前缀与精确路径（`/webui/auth/` 浏览器登录、A2A 的 RPC 与发现端点、分享链接）；`/api/v1/health` 只对 GET/HEAD 开放，其下的变更类运维动作（重置、清空、修复、探测）走正常准入；A2A 的对端与任务审批管理路由不公开 | ✅ |
| `identity.py` | ✅ 核心 | HTTP/WS 共享身份解析；远程暴露时 pair token 或 WebUI session | ✅ |
| `cp_proxy.py` | ✅ 核心 | CP 反代 HMAC-SHA256 验签（`INTERNAL_SERVICE_KEY`） | ✅ |

---

## 依赖

- 被 `app/middleware/auth.py`、`app/middleware/ws_auth.py`、`app/middleware/host_allowlist.py` 引用
- 公开前缀会连同其下所有变更类路由一起放行：每条对外开放的变更类路由必须在 handler 内自行认证，并登记在 `tests/architecture/test_public_mutating_routes.py`
