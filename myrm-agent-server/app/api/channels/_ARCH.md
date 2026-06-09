# api/channels/

## 架构概述

渠道管理、Webhook 入站与连接测试 HTTP 层（local）。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Channel webhook API routes. | ✅ |
| `channel_ingress.py` | 模块 | Internal ingress endpoint used by Control Plane sandboxes. | ✅ |
| `dlq.py` | 模块 | Get failed messages from the Dead Letter Queue. | ✅ |
| `feishu_register.py` | 模块 | Business layer API. | ✅ |
| `instances.py` | 模块 | 频道实例管理路由。提供多实例 CRUD、显示名更新、凭证存取和配置管理端点。 | ✅ |
| `login.py` | 模块 | Business layer API router. | ✅ |
| `router.py` | 路由 | Channel 管理核心路由。提供频道状态查询、启用/禁用切换、账号绑定 CRUD 和群组管理。 | ✅ |
| `routes_management.py` | 模块 | Routes management endpoints. | ✅ |
| `schemas.py` | 模块 | Channel 管理 API 数据模型。定义 Channel 状态查询和账号绑定的 schema。 | ✅ |
| `test_connections.py` | 测试 | 频道连接测试路由。提供各频道凭据连通性验证端点，用于前端配置时实时测试。 | ✅ |
| `topics.py` | 模块 | 频道 Topic 路由。提供 Topic 列表查询、Agent 绑定和频道级默认 Agent 设置功能。 | ✅ |
| `wechat.py` | 模块 | WeChat/WhatsApp 专用路由。提供扫码登录、QR 码获取、连接状态查询和登出操作。 | ✅ |
