# webui 服务模块

## 架构概述

WebUI 辅助服务：二维码/URL 组装，以及**本地/远程单机**下的浏览器会话认证（admin 密码 + httpOnly Cookie）。

认证由控制平面处理的 **Sandbox 部署**不在此包实现。

## 文件清单

| 文件 | 职责 |
|------|------|
| `qrcode.py` | 二维码与访问 URL |
| `admin_store.py` | `~/.myrm/webui/admin.json` 管理员凭据 |
| `passwords.py` | scrypt 密码哈希 |
| `temp_token.py` | 首次 setup 临时令牌（含 `WEBUI_SETUP_TOKEN`） |
| `session.py` | 签名会话 Cookie `myrm_webui_session`；`rotate_session_signing_key` 改密后失效旧 Cookie |
| `auth_service.py` | 认证状态解析、setup/login/logout；`invalidate_all_sessions` 同步轮换 session 签名键与 `pairing.rotate_pairing_key` |
| `access_policy.py` | API 是否要求 WebUI 会话 + Cookie 解析 |
| `protection_store.py` | `require_password` GUI 开关持久化 |
| `pending_setup_store.py` | setup token 磁盘 TTL |

## HTTP 路由

见 `app/api/webui/auth_routes.py`（挂载在 `/webui` 前缀下）。

LAN 开启密码保护时，`access_policy.local_api_requires_session()` 同时约束 HTTP（`identity`）与 WebSocket（`WsAuthMiddleware`）。
