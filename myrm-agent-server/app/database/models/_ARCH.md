# database/models — ORM 模型包

## 架构概述

按业务域拆分的 SQLAlchemy ORM 模型包。`__init__.py` 统一 re-export 所有模型，
外部统一使用 `from app.database.models import X` 导入，无需感知内部子模块结构。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 核心 | 包入口，统一 re-export 所有模型 | ✅ |
| `base.py` | 核心 | DeclarativeBase 基类 | ✅ |
| `chat.py` | 域模块 | Chat, Message, ConversationFork | ✅ |
| `agent.py` | 域模块 | Agent (含 tool_gateway_config), AgentSecret, AgentProfileSnapshot（WebUI rollback SSOT） | ✅ |
| `agent_history.py` | 域模块 | AgentProfileHistory（乐观锁 version 审计 + Prompt 浏览，非 rollback SSOT） | ✅ |
| `memory.py` | 域模块 | ProfileAttribute, ProceduralRule, PendingMemory, SharedContextModel, SharedContextBindingModel, SharedContextWriteProposalModel, MemoryOperationEventModel, MemoryHealthSnapshotModel, MemoryMigrationProvenanceModel, MemoryImportDryRunModel, MemoryImportBatchModel, MemoryImportItemModel, MemoryArchiveRestoreBatchModel, MemoryArchiveRestoreItemModel；导入审查和归档恢复模型持久化 dry-run、确认批次、回滚状态和清理所需时间字段 | ✅ |
| `config.py` | 域模块 | UserConfig | ✅ |
| `agent_event.py` | 域模块 | AgentTurn, AgentEvent | ✅ |
| `cron.py` | 域模块 | CronJobModel, CronRunModel, MonitorStateModel | ✅ |
| `channel.py` | 域模块 | ChannelPairingModel | ✅ |
| `media.py` | 域模块 | BatchImageJob, MediaLibrary | ✅ |
| `security.py` | 域模块 | UserToolAllowlist, RiskRule, RiskHit, SecurityProfile, SkillPermissionGrant, SkillPermissionUsageLog | ✅ |
| `skill.py` | 域模块 | PendingEvolution (deprecated), PendingMigration, ExperienceLedgerEvent | ✅ |
| `approval.py` | 域模块 | ApprovalRecord | ✅ |
| `notification.py` | 域模块 | SystemNotification | ✅ |
| `project.py` | 域模块 | Project（会话项目分组及工作区，含 workspace_path 字段） | ✅ |
| `kanban.py` | 域模块 | KanbanBoardModel, KanbanTaskModel（看板/任务 ORM，含 attachment_ids_json） | ✅ |
| `message_filter.py` | 域模块 | MessageFilterConfig, MessageFilterRule, MessageFilterAudit, MessageFilterConfigHistory | ✅ |
| `widget_kv.py` | 域模块 | WidgetKVEntry（沙箱 widget iframe KV 持久化存储） | ✅ |
| `daily_wrap.py` | 域模块 | DailyWrapCache（AI 生成的每日战报缓存） | ✅ |

## 模块依赖

- 内部：所有域模块 → `base.py` (Base 基类)
- 外部：`agent.py` → `app.ai_agents.personality_templates` (DEFAULT_PERSONALITY_STYLE)
