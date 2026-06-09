# api/extension/ 模块架构

## 架构概述

Chrome MV3 浏览器扩展桥 HTTP/WebSocket 入口：扩展经 WebSocket 维持 CDP 代理连接，WebUI 经 REST 管理授权域名与连接状态。业务逻辑见 [services/extension/_ARCH.md](../../services/extension/_ARCH.md)；客户端见 [myrm-agent-extension/_ARCH.md](../../../../myrm-agent-extension/_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 导出 `router` 与 `ws_router` | ✅ |
| `router.py` | 核心 | WebSocket `/api/v1/ws/extension` + REST 状态/域名/标签页/断开 | ✅ |

## 路由（前缀 `/api/v1`）

| 方法 | 路径 | 职责 |
|------|------|------|
| WS | `/ws/extension?token=` | 扩展持久连接；`token` 对齐 `settings.extension_auth_token` |
| GET | `/extension/status` | 连接状态、版本、授权域名、可用标签页、`token_required`（是否配置扩展 token） |
| GET | `/extension/domains` | 读取授权域名列表 |
| PUT | `/extension/domains` | 更新授权域名（`*.example.com` 通配） |
| GET | `/extension/tabs` | 列出扩展暴露的标签页 |
| POST | `/extension/disconnect` | 主动断开扩展连接 |

## 模块依赖

- `app.services.extension.bridge` — `ExtensionBridgeService` 单例
- `app.config.settings` — `extension_auth_token`
- `app.core.infra.ws_origin_guard` — WebSocket Origin 校验（挂载层）
