# skills/

## 架构概述

技能市场、安装与详情配置 UI。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `CuratorSettingsPanel.tsx` | 组件 | Skill Curator 自动提炼策略设置 | ✅ |
| `EvolutionStrategyConfig.tsx` | 组件 | 技能进化策略（Shadow A/B、阈值）配置 | ✅ |
| `LocalPathsConfig.tsx` | 组件 | 本地技能扫描路径配置 | ✅ |
| `ScanConfirmDialog.tsx` | 组件 | 目录扫描发现新技能确认对话框 | ✅ |
| `SkillBatchImportDialog.tsx` | 组件 | 批量导入技能包（zip/url）；通过 `services/archiveSecurityErrorCore` 按后端 `error_code` 稳定映射预览/导入失败文案。 | ✅ |
| `__tests__/SkillBatchImportDialog.test.tsx` | 测试 | 组件级回归：preview/confirm 失败时按 `error_code` 映射用户文案与 toast 分支。 | ✅ |
| `SkillCard.tsx` | 核心 | 技能列表卡片（信任态/版本/快捷操作） | ✅ |
| `SkillDetailDialog.tsx` | 辅助 | 技能详情 Modal 变体（小屏） | ✅ |
| `SkillDetailSheet.tsx` | 核心 | 技能详情侧边栏入口（编排 hook 与内容组件、信任/删除确认对话框） | ✅ |
| `useSkillDetailSheet.ts` | 辅助 | 技能详情状态管理 hook（内容加载/信任/env/进化锁/优化） | ✅ |
| `SkillDetailSheetContent.tsx` | 辅助 | 技能详情滚动内容区（元信息/安全扫描/存储路径/生命周期/SKILL.md 渲染） | ✅ |
| `SkillDetailHelpers.tsx` | 辅助 | 技能详情辅助组件（RequirementRow/SecurityScan/KnownPitfalls） | ✅ |
| `SkillDiscoverTab.tsx` | 组件 | 技能发现/市场浏览 Tab | ✅ |
| `SkillDraftReviewPanel.tsx` | 组件 | AI 生成技能草稿审阅面板 | ✅ |
| `SkillEmptyState.tsx` | 辅助 | 无技能空状态引导 | ✅ |
| `SkillExportDialog.tsx` | 组件 | 导出技能为 zip/marketplace 包 | ✅ |
| `SkillFilters.tsx` | 辅助 | 技能列表过滤（类别/信任/来源） | ✅ |
| `SkillGrowthCaseCard.tsx` | 核心 | 技能进化提案卡片：列表 summary + 展开/修订时 lazy 拉 detail；Simple/Detailed 双视图、Monaco DiffEditor 就地修订、审批/拒绝 | ✅ |
| `SkillHistoryPanel.tsx` | 核心 | 技能进化历史面板：已处理记录列表、一键回滚（接 evolution API） | ✅ |
| `SkillInstanceManager.tsx` | 组件 | 多实例技能版本并存管理 | ✅ |
| `SkillList.tsx` | 核心 | 技能网格/列表主视图 | ✅ |
| `SkillPermissionApprovalDialog.tsx` | 组件 | 技能运行时权限请求审批 | ✅ |
| `SkillPermissionUsageDashboard.tsx` | 组件 | 技能权限使用统计仪表盘 | ✅ |
| `SkillPermissionsManager.tsx` | 组件 | 技能权限 allowlist 编辑 | ✅ |
| `SkillQualityGuardian.tsx` | 核心 | Shadow A/B：idle 启动、running promote/stop（i18n） | ✅ |
| `SkillVersionsPanel.tsx` | 核心 | 技能版本列表、diff 对比、版本回滚（接 skill-optimization API） | ✅ |
| `SkillSyncIndicator.tsx` | 辅助 | 技能与远端同步状态指示 | ✅ |
| `SkillUploadDialog.tsx` | 组件 | 上传本地技能包对话框 | ✅ |
| `SkillUrlImportDialog.tsx` | 组件 | 从 URL 导入技能对话框 | ✅ |
| `skillCategories.ts` | 辅助 | 技能分类常量与 i18n 键映射 | ✅ |
| `PendingEvolutionsDashboard.tsx` | 核心 | 待审核技能进化列表（cases API total + stats 顶栏/filter 计数）；卡片展开按需 detail；Simple/Detailed 视图切换（localStorage 持久化） | ✅ |
| `pendingEvolutionsDashboardShared.tsx` | 辅助 | Dashboard 过滤器常量、`matchesFilter`、`SummaryCard` 子组件 | ✅ |
| `EvolutionRejectionDashboard.tsx` | 核心 | 技能进化拒绝/失败审计面板 | ✅ |

## 依赖

- `@/store/*`、`@/services/*`、`@/components/primitives/*`
- 父模块 [`features/_ARCH.md`](../_ARCH.md)
