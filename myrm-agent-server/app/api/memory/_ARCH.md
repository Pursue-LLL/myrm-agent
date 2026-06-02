# api/memory 模块架构


---

## 架构概述

用户记忆管理接口。提供记忆 CRUD、待处理记忆审批、备份归档、单用户 Memory Archive 导出与 dry-run 结构审查、Myrm archive memory section 服务端绑定导入审查、个人大脑指挥中心、独立 Memory Diagnostics 动作、纯导入计划确认、账本型回滚预演、含 missing/conflict/failed 计数与 exact ref drilldown / integrity status 的回滚，以及 Shared Context 共享上下文治理和记忆依赖健康检查。

所有 API 通过框架层 `MemoryManager` 操作记忆，不直接访问存储后端。
共享上下文 API 属于 Server 产品层，只管理 `shared:<context_id>` namespace、业务绑定、历史证据提升和写入提案，不恢复 team memory 语义。
写入提案的批准物化由 `app/services/memory/shared_context_materializer.py` 负责，API 层只做 HTTP 契约映射，并把 embedding/LLM 依赖失败转换为结构化 AI 服务错误，避免用户看到不透明 500；`shared_context_health.py` 提供低成本配置检查和可选实时 embedding 探测，提前暴露不可用依赖。

---

## 文件清单

| 文件 | 地位 | 职责| I/O/P |
|------|------|------|-------|
| `router.py` | ✅ 入口 | 子路由注册 |
| `command_center_schemas.py` | ✅ 辅助 | 个人大脑指挥中心响应模型：概览、记忆空间、治理待办、健康、事件流、事件 metadata、影响证据、成本/缓存、冲突替代、回放覆盖层、replay event trail、瀑布流、运行级检索轨迹、Memory Doctor 诊断、migration integrity、带 impact/next action/auto-fix/retry/audit/SLO/repair plan/benchmark summary 的可执行 diagnostic run/probe、MemoryCommandBenchmarkSummary（结构化 benchmark 指标：R@K/NDCG/MRR/P@K/Latency+分类明细）、repair execution、eval checks、外部连接器状态、隐私信号、含导入回滚与归档恢复健康计数的 metadata-only 部署边界摘要、迁移、自动诊断和清理指标、Knowledge Graph 可视化（节点/边/统计） |
| `operations/command_center.py` | ✅ 核心 | 个人大脑指挥中心快照、事件流、含导入回滚健康的 metadata-only plane summary、治理动作、独立 Memory Diagnostics 动作和结构化 repair executor 接口、Knowledge Graph 数据端点（节点/边/统计），聚合单用户/单沙箱记忆运行状态，并区分动作执行完成与诊断发现异常 |
| `operations/crud.py` | ✅ 核心 | 记忆 CRUD 接口（创建、列表、编辑、删除、搜索、统计、纠正、评分、状态变更、偏好摘要、Memory Archive 导出与结构 dry-run、导入 dry-run、按 dry_run_id 确认导入并自动诊断、按 dry_run_id/import_batch_id 返回账本条目/可回滚/跳过/冲突/缺失和结构化 warning 的回滚预演并执行返回 exact ref drilldown 与 integrity status 的回滚；直接导入路径拒绝绕过审查） |
| `operations/pending.py` | ✅ 核心 | 待处理记忆接口（列表、批准、拒绝、批量操作）；审批动作同步写入 Experience Ledger |
| `operations/shared_contexts.py` | ✅ 核心 | Shared Context 共享上下文接口（上下文 CRUD、按上下文/运行目标查询绑定、agent/channel/cron/conversation/task 绑定、写入提案编辑与审批） |
| `operations/shared_context_health.py` | ✅ 核心 | Shared Context 记忆健康接口（embedding 配置检查和可选实时探测） |
| `operations/shared_context_history.py` | ✅ 核心 | Shared Context 历史证据接口（会话历史搜索、历史消息提升为写入提案） |
| `operations/shared_context_migration.py` | ✅ 核心 | Shared Context 迁移接口（legacy team-visible 记忆非破坏性迁移到 `shared:legacy-team`） |
| `operations/shared_context_serializers.py` | ✅ 辅助 | Shared Context ORM 到响应模型转换 |
| `schemas.py` | ✅ 辅助 | 通用记忆请求/响应 Pydantic 模型（含 MemoryItem 投影字段、UpdateMemoryStatusRequest、TasteSummaryResponse、MemoryExportResponse、备份、评分和偏好稳定性响应） |
| `archive_schemas.py` | ✅ 辅助 | Memory Archive 与服务端绑定导入/回滚请求响应模型（含 MemoryArchiveExportResponse、MemoryArchiveDryRunRequest/Response、带 payload_hash/plan_hash 强绑定的 MemoryArchiveRestoreConfirmRequest、恢复后诊断状态、MemoryImportDryRunRequest/Response、MemoryImportConfirmRequest/Response、结构化 MemoryImportRollbackWarning、含 missing_items 的 MemoryImportRollbackPreviewResponse 和含 deleted/missing/forbidden/failed refs 与 integrity_status 的 MemoryImportRollbackResponse） |
| `shared_context_schemas.py` | ✅ 辅助 | Shared Context 专用请求/响应 Pydantic 模型 |
| `utils.py` | ✅ 辅助 | `get_memory_manager()` 工厂 + `memory_to_item()` 转换（含投影映射） + `parse_memory_type()` 验证 |

---

## 依赖关系

- **框架**：`myrm_agent_harness.toolkits.memory`（MemoryManager、MemoryType、types）
- **App**：`app/core/memory/adapters/setup.py`（create_memory_manager）
- **DB**：`app/database/`（PendingMemory ORM）
- **服务**：`app/services/memory/command_center.py`（MemoryCommandCenterService）、`app/services/memory/command_center_insights.py`（MemoryCommandCenterInsights）、`app/services/memory/diagnostics.py`（MemoryDiagnosticsService）、`app/services/memory/diagnostic_repair_executor.py`（MemoryDiagnosticRepairExecutor）、`app/services/memory/import_adapter_registry.py`（导入来源状态目录）、`app/services/memory/import_adapters.py`（导入 dry-run adapter）、`app/services/memory/import_sessions.py`（服务端绑定导入审查会话、账本型批次回滚、会话清理）、`app/services/memory/import_session_data.py`（导入会话数据转换）、`app/services/memory/import_session_models.py`（导入会话服务层 DTO）、`app/services/memory/import_ledger.py`（导入批次/条目账本状态机）、`app/services/memory/import_rollback.py`（导入回滚辅助）、`app/services/memory/command_center_projection_utils.py`（指挥中心投影辅助）、`app/services/memory/operation_ledger.py`（MemoryOperationLedgerService）、`app/services/memory/shared_context.py`（SharedContextService）、`app/services/memory/shared_context_health.py`（SharedContext 记忆健康检查）、`app/services/memory/shared_context_history.py`（SharedContextHistoryService）、`app/services/memory/shared_context_materializer.py`（SharedContextProposalMaterializer）
- **Auth**：`app/api/dependencies.py`（认证依赖注入）
