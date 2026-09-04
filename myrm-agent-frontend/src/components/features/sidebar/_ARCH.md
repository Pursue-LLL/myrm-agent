# sidebar/

## 架构概述

会话侧栏：项目、会话列表、搜索与拖拽排序。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
| --- | --- | --- | --- |
| `BatchOperationBar.tsx` | 组件 | 批量操作栏：会话批量选择、移动、删除、导出 ZIP（MD/JSON/HTML 格式选择 + 进度条 + 取消） | ✅ |
| `ChatHistoryList.tsx` | 核心 | 会话历史列表：搜索过滤、日期分组、无限滚动、DnD pin 排序（独立 grip）、Fork/Handoff/自动化等操作编排；**Tauri** 侧栏会话 drag→composer `@chat` cite（含 pinned，#5b） | ✅ |
| `ChatHistoryRow.tsx` | 核心 | 单行会话条目：右键菜单（Pin/Fork/Handoff/Automation/MoveToProject/Rename/Export/Print/Share/RevealArtifacts/CaptureEvalCase/Delete）；Tauri 可 drag 到 composer 引用 prior_chat；`SortablePinnedRow` pin 排序 grip 与 cite drag 分离 | ✅ |
| `__tests__/SortablePinnedRow.test.tsx` | 测试 | pinned 行：pin reorder grip 与 session cite draggable 分离 | ✅ |
| `__tests__/ChatHistoryRow.reveal.test.tsx` | 测试 | 单行会话产物文件夹定位菜单项与状态触发单元测试 | ✅ |
| `__tests__/useChatActionsReveal.test.tsx` | 测试 | useChatActions 会话产物目录定位动作、Toast 状态映射与异常处理单元测试 | ✅ |
| `__tests__/CaptureEvalCaseDialog.test.tsx` | 测试 | CaptureEvalCaseDialog 单元测试：覆盖数据集拉取、切换新建、确认提交与状态流转 | ✅ |
| `CaptureEvalCaseDialog.tsx` | 组件 | 会话一键沉淀为评测用例对话框：拉取已有数据集或输入新数据集，将当前会话提取并固化为私有回归用例 | ✅ |
| `HandoffDialog.tsx` | 组件 | 会话 Handoff 到其他 Agent/设备的确认对话框 | ✅ |
| `MobileDragButton.tsx` | 辅助 | 移动端侧栏拖拽排序手柄 | ✅ |
| `ProjectBar.tsx` | 核心 | 项目切换与创建顶栏；右键菜单：重命名、颜色、工作目录、默认智能体 | ✅ |
| `ProjectDefaultAgentDialog.tsx` | 组件 | 项目默认智能体选择弹窗，供 ProjectBar 右键菜单调用 | ✅ |
| `ProjectMilestonePanel.tsx` | 核心 | 当前项目里程碑面板：增删改完成 + 双击内联重命名 + 实时进度条（batch-progress API 驱动）+ 评估工件导入（按 `project_id` 过滤并优先展示可导入语义候选的一键导入 + 手动 artifact id 兜底）、导入回执提示与后端语义化错误提示；优先基于 `import_reason` 结构化错误字段映射（并保留文案兜底），并上报导入漏斗埋点（attempt/success/fail_reason）；面板内展示近 30 天导入后任务完成价值锚点。 | ✅ |
| `assessmentImportError.ts` | 辅助 | 评估导入错误解析核心：解析后端 `import_reason`（及兜底文案）映射到 i18n key，并输出机器可读 `failure_reason` 供漏斗埋点复用 | ✅ |
| `Sidebar.tsx` | 核心 | 侧栏根容器：宽度响应式、折叠态与键盘导航 | ✅ |
| `ShareConversationDialog.tsx` | 组件 | 对话分享对话框：四态展示（loading / 活跃链接 / 密码保护 / 已撤回）+ 创建（TTL+可选密码）/复制/撤销 | ✅ |
| `UserMenu.tsx` | 组件 | 用户菜单（Settings、批量优化 `userMenu.batchOptimization`→`/batch-optimization`、Brain Console 等） | ✅ |
| `constants.ts` | 辅助 | 侧栏布局与 DnD 常量 | ✅ |
| `dateGroupUtils.ts` | 辅助 | 会话按 Today/Yesterday/Earlier 分组纯函数 | ✅ |
| `useBatchMode.ts` | Hook | 批量选择模式开关与选中 ID 集合 | ✅ |
| `useChatActions.ts` | Hook | 会话 Pin/Rename/Delete/Export/Print/CaptureEvalCase 等 imperative 动作；分享：打开对话框先查询分享状态（活跃链接/密码保护/已撤回），创建与撤销 | ✅ |
| `useSidebarState.ts` | Hook | 侧栏展开/折叠、搜索词、滚动位置持久化 | ✅ |

## 依赖

- `@/store/*`、`@/services/*`、`@/components/primitives/*`
- 父模块 [`features/_ARCH.md`](../_ARCH.md)
