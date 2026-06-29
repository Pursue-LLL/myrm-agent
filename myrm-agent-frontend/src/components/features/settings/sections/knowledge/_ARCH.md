# settings/sections/knowledge 模块架构

## 架构概述

记忆 Tab 容器与子 Section：记忆浏览器、Wiki、迁移向导、备份与监控。迁移 Wizard 仅支持 Hermes / OpenClaw / Claude Code / Codex 四源自动发现（与 server `services/migration/_ARCH.md` 封闭集合一致）。

## 文件清单

| 文件 | 地位 | 职责 |
|------|------|------|
| `MemoryCenterSection.tsx` | 容器 | 记忆 Tab 路由（explorer / backup / archival / follow-ups / migration） |
| `FollowUpsPanel.tsx` | 核心 | 智能跟进列表（list / dismiss / snooze） |
| `MemorySection.tsx` | 核心 | 记忆浏览器与 CRUD |
| `MigrationWizardSection.tsx` | 核心 | 四源迁移向导（scan → preview → result）；支持 `?source=` 深链自动 preview | 
| `MigrationWizardSteps.tsx` | 核心 | 向导步骤 UI（ScanStep / PreviewStep / ResultStep）；OpenClaw episodic 勾选仅当 scan 含 openclaw 源，且 preview API 对非 openclaw 强制 `include_episodic=false` |
| `MigrationPendingReviewSection.tsx` | 辅助 | 待审核迁移技能队列 |
| `MemoryArchivalSection.tsx` | 辅助 | 归档导入/导出 |
| `MemoryBackupSection.tsx` | 辅助 | 本地备份 |
| `RemoteBackupSection.tsx` | 辅助 | 远程备份 |
| `MemoryGuardianCard.tsx` | 辅助 | Memory Doctor 入口卡片 |
| `MemoryMonitorCard.tsx` | 辅助 | 记忆健康监控 |
| `WorkingStateCard.tsx` | 辅助 | Working Memory 状态卡片。展示/编辑/清除跨会话工作记忆 |
| `WikiSection.tsx` | 容器 | Wiki 子 Tab |
| `wiki/` | 子模块 | Wiki 概念树与编辑（见 [wiki/_ARCH.md](wiki/_ARCH.md)） |

## 依赖

- `@/services/migrationDiscovery.ts` — discover API 客户端
- `@/services/memoryArchive.ts` — dry-run / confirm import
- [sections/_ARCH.md](../_ARCH.md)
