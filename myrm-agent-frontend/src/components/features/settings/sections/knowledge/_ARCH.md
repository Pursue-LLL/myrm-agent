# knowledge/

## 架构概述

Settings 记忆与知识子系统：记忆浏览、Wiki、Checkpoint、外部助手迁移 Wizard、待审队列与备份。

## 文件清单

| 文件                                | 地位   | 职责                                                                                                   | I/O/P |
| ----------------------------------- | ------ | ------------------------------------------------------------------------------------------------------ | ----- |
| `MemorySection.tsx`                 | 核心   | 记忆 Settings 主面板：提取/会话搜索/预压缩等 toggle 与 Guardian                                        | ✅    |
| `BrandStudioSettingsSection.tsx`    | 组件   | Settings 品牌风格入口（委托 `brand-studio/BrandStudioSection`）                                        | ✅    |
| `MemoryCenterSection.tsx`           | 组件   | 记忆中心入口聚合（子路由切换）                                                                         | ✅    |
| `MemoryGuardianCard.tsx`            | 组件   | 记忆 Guardian 状态卡片                                                                                 | ✅    |
| `MemoryGuardianDigestPanel.tsx`     | 组件   | 记忆 Guardian 每日摘要面板                                                                             | ✅    |
| `MemoryGuardianPolicyPanel.tsx`     | 组件   | 记忆 Guardian 策略配置面板                                                                             | ✅    |
| `MemoryMonitorCard.tsx`             | 组件   | 记忆用量/健康监控                                                                                      | ✅    |
| `WorkingStateCard.tsx`              | 组件   | Working state 展示                                                                                     | ✅    |
| `MemoryBackupSection.tsx`           | 组件   | 记忆备份导出/导入 UI                                                                                   | ✅    |
| `RemoteBackupSection.tsx`           | 组件   | 远程备份配置                                                                                           | ✅    |
| `CheckpointSection.tsx`             | 组件   | Checkpoint 快照管理                                                                                    | ✅    |
| `FollowUpsPanel.tsx`                | 组件   | Commitment / Follow-up 面板                                                                            | ✅    |
| `ObsidianVaultActions.tsx`          | 组件   | Obsidian vault 操作（导出/绑定）                                                                       | ✅    |
| `SecondBrainSetupCard.tsx`          | 组件   | Second Brain 初始化引导卡                                                                              | ✅    |
| `SecondBrainPitfallGuardrails.tsx`  | 组件   | Second Brain 落地陷阱护栏                                                                              | ✅    |
| `CodexWikiCompletionLane.tsx`       | 组件   | Codex Wiki 补全泳道                                                                                    | ✅    |
| `WikiSection.tsx`                   | 核心   | Wiki Settings 入口                                                                                     | ✅    |
| `WikiSourceSyncPanel.tsx`           | 组件   | Wiki 外部来源同步配置（Feishu/Gmail/GDrive/RSS + 手动同步）                                            | ✅    |
| `WikiIgnorePanel.tsx`               | 组件   | `.wikiignore` 编辑（Settings → Wiki · agent scope）                                                    | ✅    |
| `WikiDuplicateReviewPanel.tsx`      | 组件   | Raw corpus dedup 审核面板                                                                              | ✅    |
| `WikiQueuePanel.tsx`                | 组件   | Wiki 入库队列                                                                                          | ✅    |
| `WikiPendingEdits.tsx`              | 组件   | Wiki 待审编辑                                                                                          | ✅    |
| `WikiConceptsList.tsx`              | 组件   | Wiki 概念列表                                                                                          | ✅    |
| `WikiScopeChip.tsx`                 | 组件   | Wiki 作用域标记 chip                                                                                   | ✅    |
| `WikiAgentScopeContext.tsx`         | 组件   | Wiki agent scope 上下文                                                                                | ✅    |
| `WikiCompilePhaseBar.tsx`           | 组件   | Wiki 编译阶段进度条                                                                                    | ✅    |
| `WikiHealthIssuesSection.tsx`       | 组件   | Wiki 健康报告入口（lint issues + duplicate/synthesis 快捷入口）                                        | ✅    |
| `MigrationWizardSection.tsx`        | 核心   | 外部助手迁移 Wizard 容器与步骤路由                                                                     | ✅    |
| `MigrationWizardSteps.tsx`          | 核心   | Wizard 各步骤 UI；**ResultStep** 含迁移完成后的 **一键开启历史会话搜索**（`enableConversationSearch`） | ✅    |
| `MigrationWizardReadiness.ts`       | 辅助   | 导入 readiness 状态样式与 issue 格式化                                                                 | ✅    |
| `MigrationVaultBindPanel.tsx`       | 组件   | 迁移完成后 workspace vault 绑定候选 UI                                                                 | ✅    |
| `MigrationPendingReviewSection.tsx` | 组件   | 迁移后待审资产                                                                                         | ✅    |
| `useWikiIngestSubscription.ts`      | Hook   | Wiki ingest SSE 订阅                                                                                   | ✅    |
| `wikiDedupPoll.ts`                  | Hook   | Wiki dedup 状态轮询                                                                                    | ✅    |
| `wikiQueuePoll.ts`                  | Hook   | Wiki 队列状态轮询                                                                                      | ✅    |
| `wiki/`                             | 子模块 | Wiki 树/概念详情；见 [`wiki/_ARCH.md`](wiki/_ARCH.md)                                                  | ✅    |

## 测试

| 路径                                                        | 职责                                                                                       |
| ----------------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| `__tests__/MigrationWizardReadiness.test.ts`                | MigrationWizard 就绪状态与 issue code（含 step_budget_low 等）格式化及动作解析             |
| `__tests__/MigrationWizardSteps.resultReadiness.test.tsx`   | ResultStep readiness 门禁、Migration readiness anchor、**conversation search opt-in 按钮** |
| `__tests__/CodexWikiCompletionLane.test.tsx`                | Codex Wiki 补全泳道渲染                                                                    |
| `__tests__/MemoryGuardianCard.test.tsx`                     | 记忆 Guardian 卡片状态展示                                                                 |
| `__tests__/SecondBrainPitfallGuardrails.test.tsx`           | Second Brain 陷阱护栏文案/条件渲染                                                         |
| `__tests__/WikiPendingEdits.scope.test.tsx`                 | 待审编辑作用域（含来源对话跳转）                                                           |
| `__tests__/WikiSection.wikiEvidence.test.tsx`               | Wiki 证据展示                                                                              |
| `__tests__/wikiDedupPoll.test.ts`                           | dedup 轮询 hook                                                                            |
| `__tests__/wikiQueuePoll.test.ts`                           | 队列轮询 hook                                                                              |
| `wiki/__tests__/wikiSectionUtils.test.ts`                   | Wiki section 工具函数                                                                      |
| `wiki/__tests__/wikiTreeUtils.test.ts`                      | 树工具 + 溯源 frontmatter 解析（source_chat/source_message）                               |
| `wiki/__tests__/WikiConceptDetailPanel.sourceJump.test.tsx` | 概念详情来源对话消息级/会话级跳转                                                          |

## 依赖

- `@/store/useConfigStore` — 记忆策略（含 `memoryEnableConversationSearch`）
- `@/services/memory/archive`、`@/services/migrationDiscovery`
- 父模块 [`settings/sections/_ARCH.md`](../_ARCH.md) · [`features/_ARCH.md`](../../../_ARCH.md)
