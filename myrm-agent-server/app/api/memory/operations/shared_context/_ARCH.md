# api/memory/operations/shared_context 子包架构

## 架构概述

记忆运维 HTTP 层中的**共享上下文（Shared Context）子域**：CRUD、健康检查、历史证据检索与提案生成、遗留 team-memory 一次性迁移，以及 ORM→响应模型序列化辅助。`__init__.py` 为聚合门面统一 re-export 各 `shared_context_*` 模块的 `router`/序列化函数；各 router 由 `api.memory.router` 统一挂载。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 门面 | 聚合 re-export 全部公共符号（routers + serializers），收敛为单入口 | ✅ |
| `shared_contexts.py` | 核心 | 共享上下文 API 操作层。提供产品层共享记忆空间治理（list/create/get bindings CRUD + event recording），不暴露 team memory 语义。router 前缀 `/shared-contexts` | ✅ |
| `shared_context_health.py` | 核心 | 共享上下文健康检查 API 操作层。提供 embedding 配置和实时探测状态，避免批准写入时才暴露不可用依赖。router `/shared-contexts/health` | ✅ |
| `shared_context_history.py` | 核心 | 共享上下文历史证据 API 操作层。提供从会话历史检索证据并生成可审批提案的产品入口。 | ✅ |
| `shared_context_migration.py` | 核心 | 共享上下文一次性迁移 API：`POST /migrate-legacy-team` 将 team-visible 记忆并入 `shared:legacy-team` namespace。 | ✅ |
| `shared_context_serializers.py` | 辅助 | 共享上下文 API 序列化辅助层。集中管理 ORM 到响应模型的无副作用转换（binding_to_item / context_to_item / proposal_to_item）。 | ✅ |

## 模块依赖

- `app.database.models` — SharedContextModel / SharedContextBindingModel / SharedContextWriteProposalModel（SQLAlchemy 行）
- `app.api.memory.router` — 统一挂载各 `shared_context_*` router
