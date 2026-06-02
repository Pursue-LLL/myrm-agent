# api/chats 模块架构


---

## 架构概述

聊天会话管理接口。提供会话的 CRUD 操作（创建、列表、详情、重命名、删除、清空）和 FTS5 全文搜索。

---

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `chat/` | 核心 | 会话 CRUD + 全文搜索接口 | ✅ |

---

## API 端点

| 方法 | 路径 | 职责 |
|------|------|------|
| `GET` | `/chats/search?q=&limit=&offset=&since=&until=` | FTS5 全文搜索历史消息（snippet 高亮 + 分页 + 时间范围过滤） |
| `GET` | `/chats/catchup` | 获取所有未读会话的追赶简报 |
| `POST` | `/chats/{chat_id}/read` | 标记会话为已读 |
| `GET` | `/chats?source=` | 会话列表（分页，支持可选 source 渠道过滤） |
| `POST` | `/chats` | 创建会话 |
| `GET` | `/chats/{chat_id}` | 会话详情 |
| `PATCH` | `/chats/{chat_id}` | 重命名会话 |
| `DELETE` | `/chats/{chat_id}` | 软删除会话（移入回收站） |
| `POST` | `/chats/batch-delete` | 批量软删除会话（移入回收站，最多50个） |
| `DELETE` | `/chats` | 清空所有会话 |
| `GET` | `/chats/trash/` | 回收站列表（分页） |
| `GET` | `/chats/trash/count` | 回收站数量（用于侧边栏 badge） |
| `POST` | `/chats/trash/{chat_id}/restore` | 从回收站恢复会话 |
| `DELETE` | `/chats/trash/{chat_id}` | 永久删除回收站中的会话 |
| `DELETE` | `/chats/trash/` | 清空回收站（永久删除所有） |
| `PATCH` | `/chats/{chat_id}/workspace` | 设置/清除会话工作目录 |
| `PATCH` | `/chats/{chat_id}/recall-exclusion` | 将会话加入或移出 Conversation Recall 召回索引 |
| `POST` | `/chats/{chat_id}/regenerate` | 标记旧 assistant 消息为 inactive sibling，返回原始 query + sibling_group_id |
| `POST` | `/chats/{chat_id}/switch-sibling` | 切换 sibling group 中的 active 消息 |
| `GET` | `/chats/{chat_id}/siblings/{sibling_group_id}` | 获取 sibling group 中所有消息的状态 |

---

## 依赖关系

- `app/database/`：会话数据模型
- `app/services/chat/chat_service.py`：聊天业务逻辑（含 `search_messages` FTS5 搜索）
- `app/api/dependencies.py`：认证依赖注入
