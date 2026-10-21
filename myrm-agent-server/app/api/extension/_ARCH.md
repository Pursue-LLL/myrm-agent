# api/extension/ 模块架构

## 架构概述

浏览器扩展桥 HTTP/WebSocket 入口。WebSocket 供 MV3 扩展持久连接；REST 供 WebUI 管理授权域名与连接状态。上级：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 导出 `router`、`ws_router` | — |
| `router.py` | 核心 | `ws://…/api/v1/ws/extension`；REST `/extension/status|domains|tabs|access-policy|disconnect|setup-hints|pairing` | ✅ |
| `routes/clip_agent.py` | 路由 | **GET/PUT /extension/clip-agent** — Wiki 剪藏 agent 范围 SSOT | ✅ |

## 依赖

- `app.services.extension.bridge::get_extension_bridge`
- `app.services.extension.clip` — clip agent UserConfig get/set
- `app.config.settings` — `extension_auth_token`
- `app.config.deploy_mode` — `is_webui_remote_mode`（remote 模式 token 强制）
- `setup-hints` / `status` 返回：`auth_token_configured`、`auth_token_required`、`cdp_endpoint_discovered`、**`relay_cdp_ready`**、**`access_policy_valid`**
- `GET/PUT /extension/access-policy` — allow-all、authorized domains、paused tab ids；PUT 推送至已连接扩展
- `POST /extension/pairing` — 返回 `code`、`http_base`、`consume_url`、`ws_url`
- `POST /extension/pairing/consume` — 一次性配对消费（首选）；`GET /extension/pairing/{code}` — 兼容路径
- `/extension/domains` 返回结构化策略告警（如 wildcard 隐式包含根域）
