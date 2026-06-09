# api/extension/ 模块架构

## 架构概述

浏览器扩展桥 HTTP/WebSocket 入口。WebSocket 供 MV3 扩展持久连接；REST 供 WebUI 管理授权域名与连接状态。上级：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 导出 `router`、`ws_router` | — |
| `router.py` | 核心 | `ws://…/api/v1/ws/extension`；REST `/extension/status|domains|tabs|disconnect|setup-hints` | ✅ |

## 依赖

- `app.services.extension.bridge::get_extension_bridge`
- `app.config.settings` — `extension_auth_token`
