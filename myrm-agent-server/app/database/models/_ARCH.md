# database/models — ORM 模型包

## 架构概述

按业务域拆分的 SQLAlchemy ORM 模型包。`__init__.py` 统一 re-export 所有模型，
外部统一使用 `from app.database.models import X` 导入，无需感知内部子模块结构。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 核心 | 包入口，统一 re-export 所有模型 | ✅ |
| `base.py` | 核心 | DeclarativeBase 基类 | ✅ |
| `api_key.py` | 域模块 | APIKey（OpenAI 兼容 API Key 模型） | ✅ |
| `batch_directory.py` | 域模块 | BatchDirectoryProjectModel（Batch 目录并行 prompt 项目） | ✅ |
| `chat.py` | 域模块 | Chat, Message, ConversationFork, OfflineDurableTask, InterruptedTurnMarker（crash auto-continue write-ahead marker） | ✅ |
| `commitment.py` | 域模块 | CommitmentModel（隐式承诺/跟进追踪） | ✅ |
| `agent.py` | 域模块 | Agent (含 tool_gateway_config, cron_post_run_verify 列), AgentSecret, AgentProfileSnapshot（WebUI rollback SSOT） | ✅ |
| `agent_history.py` | 域模块 | AgentProfileHistory（乐观锁 version 审计 + Prompt 浏览，非 rollback SSOT） | ✅ |
| `artifact.py` | 域模块 | Artifact, ArtifactVersion, ArtifactAuditLog（企业协作 Vault） | ✅ |
| `artifact_publication.py` | 域模块 | ArtifactPublication（按 hosting target 的逐目标发布状态 ORM） | ✅ |
| `artifact_share.py` | 域模块 | ArtifactShareRecord（分享链接生命周期登记：fingerprint/过期/撤销时间戳） | ✅ |
| `fission.py` | 域模块 | FissionTaskRecord（高并发子代理执行图持久化，防刷新丢失） | ✅ |
| `vault_credential.py` | 域模块 | VaultCredential | ✅ |
| `web_push_subscription.py` | 域模块 | WebPushSubscription（Web Push VAPID 订阅） | ✅ |
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
| `assessment_import.py` | 域模块 | AssessmentImportLedger（评估导入幂等台账，`project_id+artifact_version_id` 唯一约束） | ✅ |
| `assessment_import_metric.py` | 域模块 | AssessmentImportMetricEvent（评估导入漏斗观测事件：attempt/success/fail/dropped，含 `surface`、`trigger`、`failure_reason` 口径） | ✅ |
| `project.py` | 域模块 | Project（会话项目分组及工作区，含 workspace_path/description/goal_summary/default_agent_id 字段） | ✅ |
| `milestone.py` | 域模块 | Milestone（项目里程碑，阶段性目标追踪和状态流转） | ✅ |
| `kanban.py` | 域模块 | KanbanBoardModel, KanbanTaskModel（看板/任务 ORM，含 project_id/milestone_id 关联和 attachment_ids_json） | ✅ |
| `message_filter.py` | 域模块 | MessageFilterConfig, MessageFilterRule, MessageFilterAudit, MessageFilterConfigHistory | ✅ |
| `widget_kv.py` | 域模块 | WidgetKVEntry（沙箱 widget iframe KV 持久化存储） | ✅ |
| `daily_wrap.py` | 域模块 | DailyWrapCache（AI 生成的每日战报缓存） | ✅ |
| `expert_summon_metric.py` | 域模块 | ExpertSummonMetricEvent（专家召唤漏斗观测事件：曝光/搜索/召唤尝试与结果/路由应用/首条发送/丢样，含 `surface`、`trigger`、`from_search`、`used_use_case` 口径字段） | ✅ |
| `turn_capability_metric.py` | 域模块 | TurnCapabilityMetricEvent（单轮 Skill/MCP 能力覆写观测事件：提交/生效/回退/排队/完成/失败/busy 重排队/丢样，含 selected/effective 规模口径与失败原因聚合） | ✅ |
| `wiki_evidence_metric.py` | 域模块 | WikiEvidenceMetricEvent（证据链观测事件：surface/open/close/query/dropped/quality_outcome_negative，含 `context_key` 口径隔离与 retention 查询索引） | ✅ |
| `faq.py` | 域模块 | FaqCorpus（per-agent FAQ 语料库配置）, FaqEntry（Q&A 条目）, FaqHitLog（命中/未命中追踪记录） | ✅ |

## 模块依赖

- 内部：所有域模块 → `base.py` (Base 基类)
- 外部：`agent.py` → `app.ai_agents.personality_templates` (DEFAULT_PERSONALITY_STYLE)
