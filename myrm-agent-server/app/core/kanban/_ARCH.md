# core/kanban/ 模块架构

## 架构概述

Kanban 持久化适配器层 + 完成验证器。实现 Harness `KanbanStore` 和 `CompletionVerifier` Protocol。
使用 SQLAlchemy ORM 将看板、任务、运行记录、事件、依赖边(TaskEdge)持久化到 SQLite。

## 文件清单

| 文件/目录 | 地位 | 职责 | I/O/P |
|----------|------|------|-------|
| `__init__.py` | 入口 | 空模块标记 | ❌ |
| `verifier.py` | ✅ 核心 | CompletionVerifier 实现 — Hallucination Gate，分层验证：shell 硬指标（复用 harness ShellCriterion，零 LLM 成本）→ LLM semantic judge | ✅ |
| `adapters/` | ✅ 核心 | 持久化适配器子包 | — |
| `adapters/__init__.py` | 入口 | 导出 SqlAlchemyKanbanStore | ✅ |
| `adapters/sqlalchemy_store.py` | ✅ 核心 | KanbanStore 的 SQLAlchemy 实现（Board/Task/Run/Event/Edge CRUD、claim、heartbeat、zombie、DFS cycle detection、batch_task_stats 批量卡片统计、list_board_edges 全量边查询、count_tasks_by_agent 多 agent 分布统计、oldest_ready_age_seconds 停滞检测、reset_stale_running_tasks Boot Recovery） | ✅ |
| `adapters/sqlalchemy_mapping.py` | ✅ 辅助 | ORM Model ↔ Domain Entity 双向映射函数（含 `specify_max_tokens` / `auto_specify_on_create` / `default_workdir` 看板设置字段，`workspace_path` / `branch` 任务字段，`get_attachment_ids` / `set_attachment_ids` 附件 ID 读写） | ✅ |

## 依赖关系

### 内部依赖
- `myrm_agent_harness/toolkits/kanban/types`：域类型定义
- `myrm_agent_harness/agent/goals/verification/base`：VerificationResult 类型
- `myrm_agent_harness/agent/goals/verification/shell`：ShellCriterion（sandbox 命令验证）
- `app/database/models/kanban`：ORM 模型
- `app/database/connection`：数据库会话管理
- `litellm`：LLM judge 调用

### 被依赖方
- `app/services/kanban/`：KanbanService 使用 SqlAlchemyKanbanStore + KanbanCompletionVerifier

## completion_criteria 格式

支持两种格式：

1. **纯文本**：`"确保报表文件已生成"` → 仅 LLM semantic judge
2. **结构化列表**：`[{"type": "shell", "command": "test -f /output.csv"}, {"type": "semantic", "criteria": "报表包含完整数据"}]` → shell 先验（零 LLM 成本）+ semantic 后验
