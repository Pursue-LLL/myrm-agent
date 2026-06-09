# api/external_agents/

## 架构概述

外部 Agent 连接档案 HTTP 层。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | External delegated agent auth endpoints. | ✅ |
| `router.py` | 路由 | 外部 Agent 订阅鉴权 HTTP API 层。让 GUI/SaaS 用户用自有订阅驱动外部 CLI。 | ✅ |
