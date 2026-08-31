# app/api/webhook/ 模块架构

Lifecycle outbound webhook REST API。供 WebUI Settings → Integrations 管理签名 HTTP 推送端点。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `routes.py` | 核心 | CRUD `/lifecycle-webhooks`、`POST /{id}/ping`（读库 secret）、匿名 `/ping` 探测；list 掩码 secret（`has_secret`） | ✅ |
| `schemas.py` | 辅助 | Pydantic 请求/响应模型 | ✅ |

## 依赖

- `app/services/webhook/lifecycle_webhook_service.py` — 异步分发与 HMAC 签名
- `app/database/models/lifecycle_webhook.py` — 持久化
- `app/services/hosting/ssrf_guard.py` — URL 校验
