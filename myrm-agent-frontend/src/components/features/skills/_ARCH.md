# skills/

## 架构概述

技能市场、安装与详情配置 UI。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `CuratorSettingsPanel.tsx` | 组件/模块 | — | — |
| `EvolutionStrategyConfig.tsx` | 组件/模块 | — | — |
| `LocalPathsConfig.tsx` | 组件/模块 | — | — |
| `ScanConfirmDialog.tsx` | 组件/模块 | — | — |
| `SkillBatchImportDialog.tsx` | 组件/模块 | — | — |
| `SkillCard.tsx` | 组件/模块 | — | — |
| `SkillDetailDialog.tsx` | 组件/模块 | — | — |
| `SkillDetailSheet.tsx` | 组件/模块 | — | — |
| `SkillDiscoverTab.tsx` | 组件/模块 | — | — |
| `SkillDraftReviewPanel.tsx` | 组件/模块 | — | — |
| `SkillEmptyState.tsx` | 组件/模块 | — | — |
| `SkillExportDialog.tsx` | 组件/模块 | — | — |
| `SkillFilters.tsx` | 组件/模块 | — | — |
| `SkillGrowthCaseCard.tsx` | 核心 | 技能进化提案卡片：Monaco DiffEditor 就地修订、审批/拒绝（接 evolution API） | ✅ |
| `SkillHistoryPanel.tsx` | 核心 | 技能进化历史面板：已处理记录列表、一键回滚（接 evolution API） | ✅ |
| `SkillInstanceManager.tsx` | 组件/模块 | — | — |
| `SkillList.tsx` | 组件/模块 | — | — |
| `SkillPermissionApprovalDialog.tsx` | 组件/模块 | — | — |
| `SkillPermissionUsageDashboard.tsx` | 组件/模块 | — | — |
| `SkillPermissionsManager.tsx` | 组件/模块 | — | — |
| `SkillQualityGuardian.tsx` | 核心 | Shadow A/B：idle 启动、running promote/stop（i18n） | ✅ |
| `SkillVersionsPanel.tsx` | 核心 | 技能版本列表、diff 对比、版本回滚（接 skill-optimization API） | ✅ |
| `SkillSyncIndicator.tsx` | 组件/模块 | — | — |
| `SkillUploadDialog.tsx` | 组件/模块 | — | — |
| `SkillUrlImportDialog.tsx` | 组件/模块 | — | — |
| `skillCategories.ts` | 组件/模块 | — | — |
| `PendingEvolutionsDashboard.tsx` | 核心 | 待审核技能进化列表 | ✅ |
| `EvolutionRejectionDashboard.tsx` | 核心 | 技能进化拒绝/失败审计面板 | ✅ |

## 依赖

- `@/store/*`、`@/services/*`、`@/components/primitives/*`
- 父模块 [`features/_ARCH.md`](../_ARCH.md)
