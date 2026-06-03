# core/security/auth 模块架构

---

## 架构概述

单租户 HTTP/WebSocket 认证辅助：公开路径白名单 + 共享 identity 解析。HTTP 在 `auth.py`，WS 在 `ws_auth.py`。Sandbox 模式下 CP 反代流量优先经 `cp_proxy.py` HMAC 验签，再 fallback API Key / 回环。

---

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `public_paths.py` | ✅ 核心 | 无需 API Key 的路径前缀（含 `/webui/auth/` 浏览器登录） | ✅ |
| `identity.py` | ✅ 核心 | HTTP/WS 共享身份解析（CP HMAC 验签 → API Key → 回环） | ✅ |
| `cp_proxy.py` | ✅ 核心 | CP 反代 HMAC-SHA256 验签（`INTERNAL_SERVICE_KEY`） | ✅ |

---

## 依赖

- 被 `app/middleware/auth.py`、`app/middleware/ws_auth.py` 引用
