# skills/

## 架构概述

技能市场、安装与详情配置 UI。

## 文件清单

| 文件                                                            | 地位 | 职责                                                                                                                                                                                          | I/O/P |
| --------------------------------------------------------------- | ---- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----- |
| `CuratorSettingsPanel.tsx`                                      | 组件 | Skill Curator 自动提炼策略设置                                                                                                                                                                | ✅    |
| `EvolutionStrategyConfig.tsx`                                   | 组件 | 技能进化策略（Shadow A/B、阈值）配置                                                                                                                                                          | ✅    |
| `LocalPathsConfig.tsx`                                          | 组件 | 本地技能扫描路径配置                                                                                                                                                                          | ✅    |
| `LocalSkillPathScanPreviewBeforeAdoptDialog.tsx`                | 组件 | 本地技能路径预检与采纳对话框（安全门禁阻断、受控免责放行二次确认、全选联动与路径采纳）                                                                                                        | ✅    |
| `LocalSkillPreviewCard.tsx`                                     | 辅助 | 本地技能预览卡片（三级安全评分徽章、门禁阻断提示、受控免责解锁状态、违规审计明细折叠展开）                                                                                                    | ✅    |
| `__tests__/LocalSkillPathScanPreviewBeforeAdoptDialog.test.tsx` | 测试 | 本地技能预检采纳弹窗与安全门禁回归测试（空状态、评分徽章、门禁阻断禁用、受控免责放行、全选排除、风险展开）                                                                                    | ✅    |
| `ScanConfirmDialog.tsx`                                         | 组件 | 目录扫描发现新技能确认对话框                                                                                                                                                                  | ✅    |
| `SkillBatchImportDialog.tsx`                                    | 组件 | 批量导入技能包（zip/url）；通过 `services/archiveSecurityErrorCore` 按后端 `error_code` 稳定映射预览/导入失败文案。                                                                           | ✅    |
| `__tests__/SkillBatchImportDialog.test.tsx`                     | 测试 | 组件级回归：preview/confirm 失败时按 `error_code` 映射用户文案与 toast 分支。                                                                                                                 | ✅    |
| `SkillCard.tsx`                                                 | 核心 | 技能列表卡片（信任态/版本/快捷操作）                                                                                                                                                          | ✅    |
| `SkillAvailabilityNotice.tsx`                                   | 辅助 | 卡片上的不可用原因行：OAuth / MCP / xAI 走设置链接；仅依赖 env 密钥的技能给出就地「配置密钥」按钮（打开详情侧栏，密钥在其中填写）                                                             | ✅    |
| `__tests__/SkillAvailabilityNotice.test.tsx`                    | 测试 | 不可用原因行回归：env 密钥就地动作、无处理器时只读、bins 混合依赖不给密钥入口、OAuth 保留设置链接、卡片点击只触发一次详情                                                                     | ✅    |
| `SkillDetailSheet.tsx`                                          | 核心 | 技能详情侧边栏入口（编排 hook 与内容组件、信任/删除确认对话框）                                                                                                                               | ✅    |
| `useSkillDetailSheet.ts`                                        | 辅助 | 技能详情状态管理 hook（内容加载/信任/env/进化锁/优化）；保存密钥成功后刷新持有该技能的列表，使可用性随服务端重算                                                                              | ✅    |
| `useLiveSkill.ts`                                               | 辅助 | 侧栏展示用的技能取自刷新后的列表（找不到则退回打开时的快照）；侧栏自身的加载副作用仍以快照为键，列表刷新不会重载 SKILL.md、不丢失未保存的密钥输入                                             | ✅    |
| `__tests__/useSkillKeysRefresh.test.tsx`                        | 测试 | 保存密钥后的刷新路由（prebuilt 列表 / 本地扫描 / 保存失败不刷新）与 `useLiveSkill` 跟随刷新                                                                                                   | ✅    |
| `SkillDetailSheetContent.tsx`                                   | 辅助 | 技能详情滚动内容区（元信息/溯源 installed_from 渠道/安全扫描/权限使用审计/存储路径/生命周期/SKILL.md 渲染）                                                                                   | ✅    |
| `SkillDetailHelpers.tsx`                                        | 辅助 | 技能详情辅助组件（RequirementRow/SecurityScan/KnownPitfalls）                                                                                                                                 | ✅    |
| `SkillDiscoverTab.tsx`                                          | 组件 | 技能发现/市场浏览 Tab（安装后 enable toast；canonical installed_skill_id 卸载）                                                                                                               | ✅    |
| `skillDiscoverInstallToast.ts`                                  | 辅助 | Discover install API 响应 → 单条 toast 文案解析（含 partial-failure 合并）                                                                                                                    | ✅    |
| `__tests__/skillDiscoverInstallToast.test.ts`                   | 测试 | toast 解析三分支回归（append 成功/失败/普通 enable）                                                                                                                                          | ✅    |
| `SkillRegistryMirrorPanel.tsx`                                  | 组件 | ClawHub registry 镜像（国际/CN/自定义 URL）+ strict probe 拦截                                                                                                                                | ✅    |
| `SkillDraftReviewPanel.tsx`                                     | 组件 | AI 生成技能草稿审阅面板；采纳 skill 后展示 `[use name]` 与 command binding 引导                                                                                                               | ✅    |
| `SkillsLearnPanel.tsx`                                          | 组件 | Settings→Installed：三字段 + 五场景 chip → raw `/learn` → server SSOT rewrite；发送被拒时保留输入、不跳转                                                                                                                 | ✅    |
| `__tests__/SkillDraftReviewPanel.invokeGuide.test.tsx`          | 测试 | 末条 draft 采纳后 invoke 引导仍可见                                                                                                                                                           | ✅    |
| `SkillEmptyState.tsx`                                           | 辅助 | 无技能空状态引导                                                                                                                                                                              | ✅    |
| `SkillExportDialog.tsx`                                         | 组件 | 导出技能为 zip/marketplace 包；展示回归门禁用例数（`eval_cases_count`）、用后端返回 filename（含 fallback）、脱敏复核用共享的 `features/redaction/`（导出回传预览摘要，技能被改动则重新预览） | ✅    |
| `SkillGrowthCaseCard.tsx`                                       | 核心 | 技能进化提案卡片：列表 summary + 展开/修订时 lazy 拉 detail；Simple/Detailed 双视图、Monaco DiffEditor 就地修订、审批/拒绝                                                                    | ✅    |
| `SkillHistoryPanel.tsx`                                         | 核心 | 技能进化历史面板：已处理记录列表、一键回滚（接 evolution API）                                                                                                                                | ✅    |
| `SkillInstanceManager.tsx`                                      | 组件 | 多实例 CRUD；实例绑定在 Agent 配置 → Skills 中选择                                                                                                                                            | ✅    |
| `SkillList.tsx`                                                 | 核心 | 技能网格/列表主视图                                                                                                                                                                           | ✅    |
| `SkillPermissionApprovalDialog.tsx`                             | 组件 | 技能运行时权限请求审批                                                                                                                                                                        | ✅    |
| `SkillPermissionUsageDashboard.tsx`                             | 组件 | 技能权限使用统计仪表盘（SkillDetailSheetContent 权限使用审计区）                                                                                                                              | ✅    |
| `SkillPermissionsManager.tsx`                                   | 组件 | 技能权限 allowlist 编辑（SkillsSection → 权限管理 Tab）                                                                                                                                       | ✅    |
| `SkillQualityGuardian.tsx`                                      | 核心 | Shadow A/B：idle 启动、running promote/stop（i18n）                                                                                                                                           | ✅    |
| `SkillVersionsPanel.tsx`                                        | 核心 | 技能版本列表、diff 对比、版本回滚（接 skill-optimization API）                                                                                                                                | ✅    |
| `SkillSyncIndicator.tsx`                                        | 辅助 | 技能与远端同步状态指示                                                                                                                                                                        | ✅    |
| `SkillUrlImportDialog.tsx`                                      | 组件 | 从 URL 导入技能对话框（集成安全与沙箱边界披露卡、Trusted Source 强制勾选门禁，彻底阻断单 URL 静默自动安装）                                                                                   | ✅    |
| `__tests__/SkillUrlImportDialog.test.tsx`                       | 测试 | URL 导入安全门禁测试（阻断单 URL 静默安装、未勾选禁用导入、勾选后正常安装、本地与云端沙箱文案区分）                                                                                           | ✅    |
| `skillCategories.ts`                                            | 辅助 | 技能分类常量与 i18n 键映射                                                                                                                                                                    | ✅    |
| `PendingEvolutionsDashboard.tsx`                                | 核心 | 待审核技能进化列表（cases API total + stats 顶栏/filter 计数、容量池实时徽章与软硬限预警熔断治理提示）；卡片展开按需 detail；Simple/Detailed 视图切换（localStorage 持久化）                  | ✅    |
| `pendingEvolutionsDashboardShared.tsx`                          | 辅助 | Dashboard 过滤器常量、`matchesFilter`、`SummaryCard`、`CapacityPoolBadge` 与 `CapacityAlertBanner` 视觉组件                                                                                   | ✅    |
| `__tests__/PendingEvolutionsDashboard.capacity.test.tsx`        | 测试 | 容量守卫视觉状态回归：正常容量徽章展示、80% 软限预警条与归档提示、100% 硬限熔断与自愈保护说明                                                                                                 | ✅    |
| `EvolutionRejectionDashboard.tsx`                               | 核心 | 技能进化拒绝/失败审计面板                                                                                                                                                                     | ✅    |

## 依赖

- `@/store/*`、`@/services/*`、`@/components/primitives/*`
- 父模块 [`features/_ARCH.md`](../_ARCH.md)
