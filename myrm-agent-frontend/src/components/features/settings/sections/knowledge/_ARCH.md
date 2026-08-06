# knowledge/

## 架构概述

Settings 记忆与知识子系统：全局/归档记忆、Wiki、Checkpoint、外部助手迁移 Wizard、待审队列与备份。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `MemorySection.tsx` | 核心 | 记忆 Settings 主面板：提取/会话搜索/预压缩等 toggle 与 Guardian | ✅ |
| `MemoryCenterSection.tsx` | 组件 | 记忆中心入口聚合（子路由切换） | ✅ |
| `MemorySettingsToggles.tsx` | 组件 | `memoryEnableConversationSearch` 等记忆策略开关 SSOT（Wizard opt-in 复用同一 store setter） | ✅ |
| `MemoryGuardianCard.tsx` | 组件 | 记忆 Guardian 状态卡片 | ✅ |
| `MemoryMonitorCard.tsx` | 组件 | 记忆用量/健康监控 | ✅ |
| `WorkingStateCard.tsx` | 组件 | Working state 展示 | ✅ |
| `MemoryBackupSection.tsx` | 组件 | 记忆备份导出/导入 UI | ✅ |
| `MemoryArchivalSection.tsx` | 组件 | 归档记忆管理 | ✅ |
| `RemoteBackupSection.tsx` | 组件 | 远程备份配置 | ✅ |
| `CheckpointSection.tsx` | 组件 | Checkpoint 快照管理 | ✅ |
| `FollowUpsPanel.tsx` | 组件 | Commitment / Follow-up 面板 | ✅ |
| `WikiSection.tsx` | 核心 | Wiki Settings 入口 | ✅ |
| `WikiQueuePanel.tsx` | 组件 | Wiki 入库队列 | ✅ |
| `WikiPendingEdits.tsx` | 组件 | Wiki 待审编辑 | ✅ |
| `WikiConceptsList.tsx` | 组件 | Wiki 概念列表 | ✅ |
| `MigrationWizardSection.tsx` | 核心 | 外部助手迁移 Wizard 容器与步骤路由 | ✅ |
| `MigrationWizardSteps.tsx` | 核心 | Wizard 各步骤 UI；**ResultStep** 含迁移完成后的 **一键开启历史会话搜索**（`enableConversationSearch`） | ✅ |
| `MigrationWizardReadiness.ts` | 辅助 | 导入 readiness 状态样式与 issue 格式化 | ✅ |
| `MigrationVaultBindPanel.tsx` | 组件 | 迁移完成后 workspace vault 绑定候选 UI | ✅ |
| `MigrationPendingReviewSection.tsx` | 组件 | 迁移后待审资产 | ✅ |
| `wiki/` | 子模块 | Wiki 树/概念详情；见 [`wiki/_ARCH.md`](wiki/_ARCH.md) | ✅ |

## 测试

| 路径 | 职责 |
|------|------|
| `__tests__/MigrationWizardSteps.resultReadiness.test.tsx` | ResultStep readiness 门禁、Migration readiness anchor、**conversation search opt-in 按钮** |
| `wiki/__tests__/wikiTreeUtils.test.ts` | Wiki 树工具函数 |

## 依赖

- `@/store/useConfigStore` — 记忆策略（含 `memoryEnableConversationSearch`）
- `@/services/memoryArchive`、`@/services/migrationDiscovery`
- 父模块 [`settings/sections/_ARCH.md`](../_ARCH.md) · [`features/_ARCH.md`](../../../_ARCH.md)
