# skills/

## 架构概述

技能市场、安装与详情配置 UI。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `CuratorSettingsPanel.tsx` | 组件/模块 | 见源码 | 见源码 |
| `EvolutionStrategyConfig.tsx` | 组件/模块 | 见源码 | 见源码 |
| `LocalPathsConfig.tsx` | 组件/模块 | 见源码 | 见源码 |
| `ScanConfirmDialog.tsx` | 组件/模块 | 见源码 | 见源码 |
| `SkillBatchImportDialog.tsx` | 组件/模块 | 见源码 | 见源码 |
| `SkillCard.tsx` | 组件/模块 | 见源码 | 见源码 |
| `SkillDetailDialog.tsx` | 组件/模块 | 见源码 | 见源码 |
| `SkillDetailSheet.tsx` | 组件/模块 | 见源码 | 见源码 |
| `SkillDiscoverTab.tsx` | 组件/模块 | 见源码 | 见源码 |
| `SkillDraftReviewPanel.tsx` | 组件/模块 | 见源码 | 见源码 |
| `SkillEmptyState.tsx` | 组件/模块 | 见源码 | 见源码 |
| `SkillExportDialog.tsx` | 组件/模块 | 见源码 | 见源码 |
| `SkillFilters.tsx` | 组件/模块 | 见源码 | 见源码 |
| `SkillGrowthCaseCard.tsx` | 组件/模块 | 见源码 | 见源码 |
| `SkillHistoryPanel.tsx` | 组件/模块 | 见源码 | 见源码 |
| `SkillInstanceManager.tsx` | 组件/模块 | 见源码 | 见源码 |
| `SkillList.tsx` | 组件/模块 | 见源码 | 见源码 |
| `SkillPermissionApprovalDialog.tsx` | 组件/模块 | 见源码 | 见源码 |
| `SkillPermissionUsageDashboard.tsx` | 组件/模块 | 见源码 | 见源码 |
| `SkillPermissionsManager.tsx` | 组件/模块 | 见源码 | 见源码 |
| `SkillQualityGuardian.tsx` | 核心 | Shadow A/B：idle 启动、running promote/stop（i18n） | ✅ |
| `SkillVersionsPanel.tsx` | 核心 | 技能版本列表、diff 对比、版本回滚（接 skill-optimization API） | ✅ |
| `SkillSyncIndicator.tsx` | 组件/模块 | 见源码 | 见源码 |
| `SkillUploadDialog.tsx` | 组件/模块 | 见源码 | 见源码 |
| `SkillUrlImportDialog.tsx` | 组件/模块 | 见源码 | 见源码 |
| `skillCategories.ts` | 组件/模块 | 见源码 | 见源码 |
| `PendingEvolutionsDashboard.tsx` | 核心 | 待审核技能进化列表 | ✅ |
| `EvolutionRejectionDashboard.tsx` | 核心 | 技能进化拒绝/失败审计面板 | ✅ |

## 依赖

- `@/store/*`、`@/services/*`、`@/components/primitives/*`
- 父模块 [`features/_ARCH.md`](../_ARCH.md)
