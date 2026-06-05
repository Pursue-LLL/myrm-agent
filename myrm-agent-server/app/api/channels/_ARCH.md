# api/channels 模块架构

## 架构概述

Channel 管理的 HTTP API 层。管理端点按功能拆分为多个路由文件，统一注册在 `/channels/manage/*` 前缀下；
Webhook 端点（`/channels/*`）接收外部平台的入站消息回调。仅在本地模式下注册管理路由。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 模块声明 | ❌ |
| `router.py` | 核心 | 状态查询（含 SDK `unavailable` 探测）、`POST …/install-dependencies`（`registered` 诚实响应）、启用/禁用切换（先 ensure 再 commit）、账号绑定 CRUD、群组管理 + `_channel_config_key` | ✅ |
| `test_connections.py` | 核心 | 16+ 频道连接测试端点（Feishu, Slack, Telegram, Discord 等） | ✅ |
| `instances.py` | 核心 | 多实例 CRUD、显示名更新、凭证存取和配置管理 | ✅ |
| `topics.py` | 核心 | Topic 发现、Agent 绑定和频道级默认 Agent 设置 | ✅ |
| `wechat.py` | 核心 | WeChat/WhatsApp 扫码登录、QR 码状态查询和登出 | ✅ |
| `schemas.py` | 核心 | Pydantic 请求/响应模型 | ✅ |
| `channel_ingress.py` | 核心 | 频道入站消息处理 | ✅ |
| `routes_management.py` | 核心 | 频道路由管理端点 | ✅ |
| `login.py` | 核心 | 频道登录流程端点 | ✅ |
| `dlq.py` | 核心 | 死信队列管理端点 | ✅ |
| `feishu_register.py` | 核心 | 飞书扫码一键创建应用（device-code flow）端点 | ✅ |

## 模块依赖

- `router.py` → `core/channel_bridge/`, `services/channels/dependency_install`, `services/channels/sdk_registration`, `channels/providers/registry`, `database/models`, `database/connection`
- `test_connections.py` → `core/channel_bridge/providers/`, `app.channels`
- `instances.py` → `routes._channel_config_key`, `core/channel_bridge/channel_factory`
- `topics.py` → `core/channel_bridge/topic_config`, `services/agent/agent_service`
- `wechat.py` → `core/channel_bridge/`, `instances._delete_instance_credentials`
- `feishu_register.py` → `app.channels.providers.feishu.registration`, `database/`, `services/config/encryption`
