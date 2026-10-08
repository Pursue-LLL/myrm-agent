# services/memory/operations 模块架构

记忆 CRUD 业务处理器与实体呈现转换。HTTP 路由在 `app/api/memory/operations/crud.py` 薄绑定 handler 函数。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `crud_handlers.py` | 门面 | 从 `crud/` 子模块 re-export 全部 handler，供路由绑定 | ✅ |
| `presentation.py` | 辅助 | 记忆实体→`MemoryItem` DTO 转换与 `parse_memory_type` 校验，供 api 与各 handler 共用 | ✅ |
| `pending_review.py` | 核心 | 审批队列（harness `pending_records`）的唯一业务审批入口：Web 弹窗、指挥中心、IM `/memory` 都经 `approve_pending` / `reject_pending` / 批量版本批准或拒绝，并尽力写入经验账本（`REVIEW_APPROVED/REJECTED`，含改写标记、提案动作与目标记忆 id）与操作账本（遗忘提案注明目标已移入回收站）；账本写入失败只记 WARNING，不影响已生效的审批；陈旧的重复提交不重复审计；同一提案的审批按 pending_id 进程内串行（多入口并发只生效一次）；批量版本逐条审批，目标已变化的提案（`PendingTargetChangedError`）计入失败并保持待审。`record_pending_event` 同时供冲突仲裁复用 | ✅ |
| `crud/_common.py` | 辅助 | `_record_memory_event`、`_SORT_KEYS` 共享工具 | ✅ |
| `crud/list_write.py` | 核心 | 列表、创建、更新、纠正、删除、搜索、统计、评分、状态变更 | ✅ |
| `crud/trash.py` | 核心 | 回收站列表、恢复、永久删除 | ✅ |
| `crud/import_archive.py` | 核心 | 导出、归档、导入 dry-run/confirm、回滚预演与执行 | ✅ |
| `crud/import_readiness.py` | 核心 | 导入就绪契约构建（`MemoryImportReadiness` 状态 + issue 码 SSOT，供 stream preflight 与设置深链） | ✅ |
| `crud/preferences.py` | 核心 | 偏好摘要、偏好列表、pin/forget/unpin/unforget | ✅ |

## 依赖关系

- `app/schemas/memory/crud.py` — CRUD 请求/响应 Schema
- `app/schemas/memory/archive.py` — 归档/导入 Schema
- `app/services/memory/archive/archive.py` — 归档服务
- `app/services/memory/imports/import_sessions.py` — 导入会话服务
