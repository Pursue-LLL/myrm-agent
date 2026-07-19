# api/memory/operations/

## 架构概述

记忆运维 HTTP 层：指挥中心、Shared Context、归档恢复、诊断。上级文档：[../../_ARCH.md](../../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Memory operations submodule | ✅ |
| `archival.py` | 模块 | Memory archival endpoints. | ✅ |
| `archive_restore.py` | 模块 | 记忆归档恢复 API 操作层。只编排请求/响应和错误映射，恢复语义由服务层负责。 | ✅ |
| `backup.py` | 模块 | Memory backup and restore endpoints. | ✅ |
| `backup_remote.py` | 模块 | Remote backup API endpoints. | ✅ |
| `command_center.py` | 模块 | 记忆指挥中心 API 操作层。将单用户/单沙箱记忆运行快照暴露给设置页 UI，含 Claim/Evidence 知识图谱（支持 namespace 过滤）。 | ✅ |
| `crud.py` | 模块 | Memory CRUD HTTP routes — thin transport layer. | ✅ |
| `guardian.py` | 模块 | 记忆守护者 API。暴露健康分与调度状态；手动维护触发支持 `safe/force` 契约；提供守护策略（频率档位 + quiet window）读写与晨间摘要查询（按最新完成维护窗口聚合）；健康/摘要读路径支持首访浏览器时区初始化，并在缺少客户端时区头时使用服务端本地时区兜底初始化（后续客户端头可自动纠偏）；`/health` 返回守卫不可用告警聚合；`/overview` 返回 health/policy/alerts + digest 单契约；告警聚合采用按 frequency tier 自适应的最小事件阈值与 escalation 阈值策略（reason count + ratio）。 | ✅ |
| `pending.py` | 模块 | 待处理记忆 API 操作层。提供待处理记忆的审批流管理。 | ✅ |
| `shared_context_health.py` | 模块 | 共享上下文健康检查 API 操作层。提供 embedding 配置和实时探测状态，避免批准写入时才暴露不可用依赖。 | ✅ |
| `shared_context_history.py` | 模块 | 共享上下文历史证据 API 操作层。提供从会话历史检索证据并生成可审批提案的产品入口。 | ✅ |
| `shared_context_migration.py` | 模块 | 共享上下文一次性迁移 API：`POST /migrate-legacy-team` 将 team-visible 记忆并入 `shared:legacy-team` namespace。 | ✅ |
| `shared_context_serializers.py` | 模块 | 共享上下文 API 序列化辅助层。集中管理 ORM 到响应模型的无副作用转换。 | ✅ |
| `shared_contexts.py` | 模块 | 共享上下文 API 操作层。提供产品层共享记忆空间治理，不暴露 team memory 语义。 | ✅ |
| `reindex.py` | 模块 | Memory reindex API — orphan detection, estimation, and execution for embedding model migration. | ✅ |
| `working_state.py` | 模块 | Working State API — cross-session task continuity endpoint. 提供读/写/清除 `__working_state` Profile 属性的 HTTP 入口。 | ✅ |
