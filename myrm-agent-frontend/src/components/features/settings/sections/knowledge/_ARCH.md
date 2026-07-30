# settings/sections/knowledge 模块架构

## 架构概述

记忆 Tab 容器与子 Section：记忆浏览器、Wiki、迁移向导、备份与监控。迁移 Wizard 仅支持 Hermes / OpenClaw / Claude Code / Codex 四源自动发现（与 server `services/migration/_ARCH.md` 封闭集合一致）。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `MemoryCenterSection.tsx` | 容器 | 记忆 Tab 路由（explorer / backup / archival / follow-ups / migration） | — |
| `FollowUpsPanel.tsx` | 核心 | 智能跟进列表（list / dismiss / snooze）；Vitest：`__tests__/FollowUpsPanel.test.tsx` | — |
| `MemorySection.tsx` | 核心 | 记忆浏览器与 CRUD；JSON 导入 confirm 后展示 readiness toast（非 ready 时 issue 文案 + 设置深链） | — |
| `MigrationWizardSection.tsx` | 核心 | 四源迁移向导（scan → preview → result）；消费 server 下发 `source_manifest` + `source_manifest_authoritative`，支持 `?source=` 深链自动 preview；Settings 路径 Result 内嵌 vault bind handoff | — |
| `MigrationWizardSteps.tsx` | 核心 | 向导步骤 UI（ScanStep / PreviewStep / ResultStep）；ResultStep Local Settings 路径展示 vault bind handoff；mount 时 silent recheck + readiness anchor | — |
| `MigrationVaultBindPanel.tsx` | 辅助 | 迁移后 project workspace bind 共享 UI（Settings Result + Onboarding sync_folder）；bind 成功 queue `boundProjectId`；若当前 chat 已存在则立即 PATCH project | — |
| `MigrationWizardReadiness.ts` | 辅助 | 迁移结果页 readiness 状态映射、issue 文案；深链 href 消费 API `issue.settings_path`，label 仍按 code i18n | — |
| `MigrationPendingReviewSection.tsx` | 辅助 | 待审核迁移技能队列 | — |
| `MemoryArchivalSection.tsx` | 辅助 | 归档导入/导出 | — |
| `MemoryBackupSection.tsx` | 辅助 | 本地备份 | — |
| `RemoteBackupSection.tsx` | 辅助 | 远程备份 | — |
| `MemoryGuardianCard.tsx` | 辅助 | Memory Guardian 产品化卡片：健康分、`safe/force` 手动维护、策略配置、晨间摘要（夜间窗口聚合）与守卫不可用聚合告警提示（`escalated` 风险色 + `dominant_reason` 可解释文案 + dominant count/ratio/threshold 解释）；通过 `overview` 单请求收敛 health/policy/alerts+digest。Vitest：`__tests__/MemoryGuardianCard.test.tsx` 覆盖 escalated/monitoring 与阈值缺失回归场景 | — |
| `MemoryGuardianPolicyPanel.tsx` | 辅助 | Memory Guardian 策略配置子面板（频率档位 + quiet window） | — |
| `MemoryGuardianDigestPanel.tsx` | 辅助 | Memory Guardian 晨间摘要子面板（维护产出、运行次数与健康变化），并区分夜间静默窗口与 rolling 24h 聚合语义 | — |
| `MemoryMonitorCard.tsx` | 辅助 | 记忆健康监控 | — |
| `WorkingStateCard.tsx` | 辅助 | Working Memory 状态卡片。展示/编辑/清除跨会话工作记忆 | — |
| `WikiSection.tsx` | 容器 | Wiki 子 Tab；Overview **ObsidianVaultActions** + **WikiSourceSyncPanel** + synthesis badge + SecondBrainSetupCard；Query 结果 snippet 卡片 → SourceChunkDrawer（含 `claim_status`） | ✅ |
| `WikiSourceSyncPanel.tsx` | 核心 | Overview 外部来源同步（Gmail/GDrive/RSS/镜像/上次同步/Drive 重连引导）；响应式 Card | ✅ |
| `ObsidianVaultActions.tsx` | 核心 | Overview Obsidian 打开/文件夹/reveal/下载包；Open 仅 `obsidian_launch_available`；Local git 历史 hint | ✅ |
| `SecondBrainSetupCard.tsx` | 核心 | 第二大脑一键预设：apply/status checklist（含 read-it-later + wiki-morning-delta 双 cron）、toast 展示 server message（含 vault seed 计数）、自动 selectAgent、vault/provider 深链 | ✅ |
| `WikiPendingEdits.tsx` | 核心 | HITL 待审列表；**全部/概念/演变合成** 筛选 + synthesis badge；**initialFilter** prop；**agentScopeId 显式 reload** + scope chip；approve 区分 `stale_pending` / `invalid_frontmatter` toast | ✅ |
| `WikiConceptsList.tsx` | 编排 | 词条 Tab；接收 `agentScopeId` + scopeRevision remount key | ✅ |
| `WikiScopeChip.tsx` | UI | Pending/Queue scope 提示 badge | ✅ |
| `WikiAgentScopeContext.tsx` | 核心 | URL `?agentId=` scope provider（scopeRevision + scopeLabel） | ✅ |
| `WikiQueuePanel.tsx` | 核心 | 编译队列面板；pause banner + **WikiCompilePhaseBar**；failed_items；… | ✅ |
| `WikiCompilePhaseBar.tsx` | 核心 | 共享 compile phase 三阶段条（Queue + Overview 同源 SSE） | ✅ |
| `useWikiIngestSubscription.ts` | 辅助 | EventSource hook for `/wiki/ingest/stream` scoped snapshots（含 `synthesis_pending_count`） | ✅ |
| `wikiQueuePoll.ts` | 辅助 | Queue poll 纯函数（`computeShouldPollQueue`、`queueStatsDiverge`、间隔/失败阈值常量）；Vitest：`__tests__/wikiQueuePoll.test.ts` | ✅ |
| `wiki/` | 子模块 | Wiki 概念树与编辑（见 [wiki/_ARCH.md](wiki/_ARCH.md)） | — |

## 依赖

- `@/services/migrationDiscovery.ts` — discover API 客户端
- `@/services/memoryArchive.ts` — dry-run / confirm import
- [sections/_ARCH.md](../_ARCH.md)
