# memory/operations 模块架构


---

## 架构概述

记忆 API 操作层。实现记忆 CRUD、待处理记忆审核、备份归档、单用户 Memory Archive 恢复、服务端绑定导入确认、账本型导入回滚预演/回滚和 Shared Context 共享上下文治理。Shared Context 写入批准只委托服务层物化，不在 API 层直接写 MemoryManager；物化时的 embedding/LLM 依赖失败会映射为结构化 AI 服务错误，并提供独立健康检查端点提前验证 embedding 配置。

---

## 文件清单

| 文件 | 地位 | 职责| I/O/P |
|------|------|------|-------|
| `crud.py` | ✅ 核心 | 记忆 CRUD HTTP 薄路由（绑定 `services/memory/operations/crud_handlers`） |
| `archive_restore.py` | ✅ 核心 | Memory Archive 恢复操作。暴露归档恢复 dry-run、hash-gated confirm、rollback dry-run 和 rollback 端点，confirm 后自动运行内容盲 Memory Diagnostics 并回写恢复批次 metadata；恢复语义、journal 和安全预检由服务层执行 |
| `pending.py` | ✅ 核心 | 待处理记忆操作（列表、批准、拒绝、批量操作）；单条/批量审批动作写入 Experience Ledger |
| `shared_contexts.py` | ✅ 核心 | Shared Context 共享上下文操作。管理上下文 CRUD、按上下文/运行目标查询绑定、agent/channel/cron/conversation/task 绑定、写入提案创建/编辑/批准/拒绝 |
| `shared_context_health.py` | ✅ 核心 | Shared Context 记忆健康操作。返回 embedding 配置状态和可选实时探测结果 |
| `shared_context_history.py` | ✅ 核心 | Shared Context 历史证据操作。搜索会话历史并将选中消息提升为可审批写入提案 |
| `shared_context_migration.py` | ✅ 核心 | Shared Context 迁移操作。将 legacy team-visible semantic/episodic 记忆复制到 `shared:legacy-team` |
| `shared_context_serializers.py` | ✅ 辅助 | Shared Context ORM 到 Pydantic 响应模型转换 |
| `command_center.py` | ✅ 核心 | 个人大脑指挥中心 API。聚合概览、空间、治理、时间线、回放、健康和运行时面板数据，提供 consolidation rollback 端点 |
| `guardian.py` | ✅ 核心 | 记忆守护者 API。暴露记忆 4 维健康分数和定时维护调度器状态，提供手动触发维护入口 |
