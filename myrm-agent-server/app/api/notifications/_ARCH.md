# api/notifications 模块架构


## 架构概述

系统通知 API。提供通知列表、单条/全部已读标记、DLQ 重试、过期通知清理等接口。
通知支持 `action_url`（存于 `meta_data`），前端点击通知可直接跳转到相关页面。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 路由导出 | — |
| `router.py` | 核心 | 通知 REST 接口（列表、单条已读、全部已读、重试、过期清理） | ✅ |
| `schemas.py` | 辅助 | 请求/响应 Pydantic 模型 | ✅ |

## API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/notifications` | 获取通知列表（分页） |
| POST | `/notifications/read-all` | 全部标记已读 |
| POST | `/notifications/{id}/read` | 单条标记已读 |
| POST | `/notifications/{id}/retry` | 重试 DLQ 消息 |

## 清理策略

`cleanup_old_notifications()` 在服务器 warmup 阶段调用一次，清理 30 天以上的已读通知。
