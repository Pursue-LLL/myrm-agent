# api/extension/ 模块架构

## 架构概述

浏览器扩展桥 HTTP/WebSocket 入口。WebSocket 供 MV3 扩展持久连接；REST 供 WebUI 管理授权域名与连接状态。上级：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 导出 `router`、`ws_router` | — |
| `router.py` | 核心 | `ws://…/api/v1/ws/extension`（origin 守卫 + token 校验）；REST `/extension/status|domains|tabs|disconnect|clip-agent|setup-hints`（status 含 `handshake_ready` 与 extension capabilities 矩阵，setup-hints 含 remote token required 与 CDP 可发现性提示；clip-agent 为 Wiki 剪藏 agent 范围 SSOT） | ✅ |

## 依赖

- `app.services.extension.bridge::get_extension_bridge`
- `app.config.settings` — `extension_auth_token`
- `app.config.deploy_mode` — `is_webui_remote_mode`（remote 模式 token 强制）
- `setup-hints` 返回三类非敏感提示：`auth_token_configured`、`auth_token_required`、`cdp_endpoint_discovered`
- `/extension/domains` 返回结构化策略告警（如 wildcard 隐式包含根域）
