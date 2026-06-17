# middleware 模块架构


---

## 架构概述

FastAPI 全局 HTTP 中间件。提供文本清洗、认证和缓存控制。
执行顺序见 `app/server/middlewares.py`（LIFO）：TextSanitizer → HostAllowlist → SessionIdle → Auth → …

在 Agent-in-Sandbox 架构下，Server 层作为沙箱内的单用户服务实例运行，
安全防护（防重放、限流等）由控制平台或反向代理在网络层处理。

---

## 文件清单

| 文件 | 地位 | 职责 |
|------|------|------|
| `max_body_size.py` | ✅ 核心 | 全局 ASGI 熔断器：包装底层 `receive` 函数，在 ASGI 层面限制请求体总大小（如 15MB），防止超大文件上传导致的 OOM 和磁盘耗尽攻击。 |
| `text_sanitizer_middleware.py` | ✅ 核心 | 文本清洗中间件：四层防护（1）所有请求的 query 参数（2）JSON body（3）Form data body（4）LLM 输出层，移除 surrogate 字符和控制字符（调用 harness/utils/text_sanitizer） |
| `webhook_security.py` | ✅ 核心 | Webhook 安全加固中间件（原始字节防线）：在反序列化 JSON 之前强制校验请求体大小（默认 1MB），防止超大 Payload 导致单机沙箱 OOM 崩溃。 |
| `ingress.py` | ✅ 核心 | Public Ingress 强制代理纠偏中间件：监听 `/api/` 路由，将 Scheme/Host 覆写为 `get_public_ingress_base_url()`；loopback 与 RFC1918 私有 LAN Host 跳过覆写，避免本地/内网 WebUI 被 stale 公网 URL 劫持。 |
| `host_allowlist.py` | ✅ 核心 | WebUI 远程暴露时 Host 头 allowlist（DNS rebinding 防护） | ✅ |
| `session_idle.py` | ✅ 核心 | 远程暴露路径滑动刷新 WebUI session cookie（30min idle） | ✅ |
| `auth.py` | ✅ 核心 | HTTP 单租户认证；注入 admission_path/trust_zone/pair token/`pair_bound_chat_id` | ✅ |
| `ws_auth.py` | ✅ 核心 | WebSocket ASGI 握手鉴权，注入 `scope.state.user_id` 与 pair 绑定 | ✅ |
| `auth_audit.py` | ✅ 核心 | Auth 审计 JSONL（`auth.py` 在非回环认证时写入） | ✅ |
| `auth_alert.py` | ✅ 核心 | Auth 告警引擎（WebUI Remote / Sandbox） | ✅ |
| `security.py` | ⚠️ 保留 | 防重放中间件实现；**默认不 register**（SaaS 由 CP 网络层隔离） | ⚠️ |
| `cache.py` | ✅ 辅助 | 缓存中间件（路径级 Cache-Control，仅 GET 请求） |

---

## 认证模式

| 功能 | Local | Sandbox / Remote |
|------|------|------------------|
| TextSanitizer | 启用 | 启用 |
| Auth | 本机/容器回环→`local-user` | CP HMAC 验签 → `SANDBOX_API_KEY` → 回环 |
| Security (anti-replay) | 不 register | 不 register（CP 网络层） |
| Cache | 启用 | 启用 |

---

## 依赖关系

### 内部依赖
- `app/config/settings`：`SANDBOX_API_KEY`
- `app/core/security/auth/public_paths`：公开路径白名单
- `app/platform_utils/deployment_capabilities`：部署能力位
- `app/middleware/auth_audit`：审计 JSONL

### 被依赖方
- `app/main.py`：中间件注册
