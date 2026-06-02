# middleware 模块架构


---

## 架构概述

FastAPI 全局 HTTP 中间件。提供文本清洗、认证和缓存控制。
执行顺序：TextSanitizer → Auth → Cache → 应用 → Cache → Auth → TextSanitizer。

在 Agent-in-Sandbox 架构下，Server 层作为沙箱内的单用户服务实例运行，
安全防护（防重放、限流等）由控制平台或反向代理在网络层处理。

---

## 文件清单

| 文件 | 地位 | 职责 |
|------|------|------|
| `max_body_size.py` | ✅ 核心 | 全局 ASGI 熔断器：包装底层 `receive` 函数，在 ASGI 层面限制请求体总大小（如 15MB），防止超大文件上传导致的 OOM 和磁盘耗尽攻击。 |
| `text_sanitizer_middleware.py` | ✅ 核心 | 文本清洗中间件：四层防护（1）所有请求的 query 参数（2）JSON body（3）Form data body（4）LLM 输出层，移除 surrogate 字符和控制字符（调用 harness/utils/text_sanitizer） |
| `webhook_security.py` | ✅ 核心 | Webhook 安全加固中间件（原始字节防线）：在反序列化 JSON 之前强制校验请求体大小（默认 1MB），防止超大 Payload 导致单机沙箱 OOM 崩溃。 |
| `ingress.py` | ✅ 核心 | Public Ingress 强制代理纠偏中间件：监听所有 `/api/` 路由，强制覆写 ASGI 协议的 Scheme 和 Host 标头为正确的公网地址，根除代理环境下的 OAuth 重定向、Webhook 签名哈希失效以及文件上传绝对路径错误等各种隐藏的网络协议问题。 |
| `auth.py` | ✅ 核心 | HTTP 单租户认证中间件（委托 `core/security/auth/identity.py`） | ✅ |
| `ws_auth.py` | ✅ 核心 | WebSocket ASGI 握手鉴权，注入 `scope.state.user_id` | ✅ |
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
