# app/api/chats/chat/core 子包架构

会话核心路由。按资源拆子路由，`app.api.chats.chat.core` 仍只导出 `router`；父包 `chat/__init__.py` 的挂载顺序不变。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 子域出口 | 组合并导出 `router`：crud → recall → pins → session | — |
| `crud.py` | 核心 | `GET /`（分页/来源/项目过滤）、`GET/POST/DELETE /{chat_id}`、`POST /batch-delete`、`GET /{chat_id}` | — |
| `recall.py` | 核心 | `GET /recall/search`（@chat SSOT）、`GET /recall/entries`、`PATCH /{chat_id}/recall-exclusion` | — |
| `pins.py` | 核心 | `/{chat_id}/pin`、`/{chat_id}/unpin`、`PUT /pin-reorder`（`MAX_PINNED_CHATS`） | — |
| `session.py` | 核心 | `/{chat_id}/workspace`、`/fission`、`/active-moa-preset`、`/session-skills`、`/delivery-contracts`、`/tags` | — |

## 路由顺序

子路由挂载顺序为 crud → recall → pins → session。总路由共 17 条；静态路径（`/recall/*`、`/batch-delete`、`/pin-reorder`）与动态路径 `/{chat_id}` 系列在段数或方法上不重叠，顺序变化不影响匹配。

## 依赖关系

- 上游：`app.database.dto`、`app.database.repositories.chat_repo`、`app.services.chat.*`、`app.core.utils.{errors,response_utils}`
- 下游：`app/api/chats/chat/__init__.py`（`from .core import router as core_router`）
