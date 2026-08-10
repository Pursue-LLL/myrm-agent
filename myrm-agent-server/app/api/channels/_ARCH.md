# api/channels/

## 架构概述

渠道管理、Webhook 入站与连接测试 HTTP 层（local）。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Channel webhook API routes. | ✅ |
| `channel_ingress.py` | 模块 | Control Plane 沙箱内部入站：仅 `_handle_inbound` 入队；cron event dispatch 由 AgentRouter 统一处理 | ✅ |
| `dlq.py` | 模块 | Get failed messages from the Dead Letter Queue. | ✅ |
| `feishu_register.py` | 模块 | Business layer API. | ✅ |
| `instances.py` | 模块 | 频道实例管理路由。提供多实例 CRUD、显示名更新、凭证存取和配置管理端点。 | ✅ |
| `login.py` | 模块 | Business layer API router. | ✅ |
| `router.py` | 路由 | Channel 管理核心路由。提供频道状态查询、启用/禁用切换、账号绑定 CRUD、群组管理与 GitHub webhook URL 获取（Ingress 优先）。 | ✅ |
| `routes_management.py` | 模块 | Routes management endpoints. | ✅ |
| `schemas.py` | 模块 | Channel 管理 API 数据模型。定义 Channel 状态查询、账号绑定与 GitHub webhook URL 的 schema。 | ✅ |
| `test_connections.py` | 测试 | 频道连接测试路由。提供各频道凭据连通性验证端点，用于前端配置时实时测试。 | ✅ |
| `topics.py` | 模块 | 频道 Topic 路由。提供 Topic 列表查询、Agent 绑定和频道级默认 Agent 设置功能。 | ✅ |
| `wechat.py` | 模块 | WeChat/WhatsApp 专用路由。提供扫码登录、QR 码获取、连接状态查询和登出操作。 | ✅ |
| `wechat_official.py` | 模块 | WeChat Official Account 凭证测试与 HITL 草稿推送 API（uploadimg + draft/add）；路径校验 `relative_to` + workspace 未知 fail-closed (503)；合规 scan（title + resolved digest + HTML 可见正文）高危 422 hits、非高危 200 `complianceWarnings`；502 返回 locale-aware 微信 errcode 可操作提示；author ≤8；draft 流水线 inline 图先于 thumb，content 为 body+内嵌 style+formatter 块级 inline style；WebUI 文内首图封面预填。 | ✅ |
