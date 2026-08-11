# memory/

## 架构概述

记忆中心：浏览、编辑、归档与召回相关 UI。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `ConnectWizardDialog.tsx` | 组件 | 外部 AI 工具 Connect Wizard：Myrm Agent Profile 选择器 + 外部工具 profile 选择 → 生成 MCP 配置（token 携带 agent_id 作用域）→ doctor 验证 → revoke 管理 | ✅ |
| `ConversationRecallPanel.tsx` | 组件 | 历史会话召回搜索与插入面板 | ✅ |
| `MemoryArchiveRestoreDialog.tsx` | 组件 | 记忆归档批量恢复确认对话框 | ✅ |
| `MemoryCard.tsx` | 核心 | 单条记忆卡片（类型/icon/摘要/操作菜单） | ✅ |
| `MemoryClearAllDialog.tsx` | 组件 | 清空全部记忆二次确认 | ✅ |
| `MemoryCommandCenter.tsx` | 核心 | 记忆命令中心主布局入口；消费 migration manifest authoritative 语义并驱动向导深链；支持通过 URL `?project=` 或下拉筛选器按项目过滤 SharedContext 记忆空间 | ✅ |
| `MemoryCommandCenterAdvancedPanels.tsx` | 组件 | 高级面板：导入/导出/图谱/Doctor | ✅ |
| `MemoryCommandCenterChrome.tsx` | 组件 | 命令中心顶栏、Tab 与搜索框 | ✅ |
| `MemoryCommandCenterDoctorPanel.tsx` | 组件 | 记忆系统 Doctor 诊断面板；含静态检查、可执行诊断、结构化 benchmark 指标卡片与历史趋势（最近 N 次 recall@5/ndcg@5/mrr/latency p50/p95 + 上次 delta + 类别通过率 + run 状态徽章 + embedding 模型漂移提示） | ✅ |
| `MemoryCommandCenterPanels.tsx` | 组件 | 主内容区 Tab 面板编排（含 migration 最近导入 batch 的执行就绪/首轮 outcome 展示、adapter readiness 可视化与 missing 状态迁移向导动作闭环） | ✅ |
| `MemoryContextPanel.tsx` | 组件 | Shared Context 编辑与预览 | ✅ |
| `MemoryCreateDialog.tsx` | 组件 | 手动创建记忆对话框 | ✅ |
| `MemoryDetailSheet.tsx` | 组件 | 记忆详情 Sheet（全文/metadata/来源） | ✅ |
| `MemoryEditDialog.tsx` | 组件 | 编辑记忆内容与标签 | ✅ |
| `MemoryGuide.tsx` | 组件 | 首次使用记忆功能引导 | ✅ |
| `MemoryHealthDashboard.tsx` | 组件 | 记忆健康度指标仪表盘 | ✅ |
| `MemoryImportReviewDialog.tsx` | 组件 | 批量导入 dry-run 结果审阅 | ✅ |
| `MemoryKnowledgeGraph.tsx` | 组件 | 记忆知识图谱 force-graph 可视化 | ✅ |
| `MemoryLayerGuide.tsx` | 组件 | Command Center 记忆分层说明卡（工作集/任务状态/长期记忆/原始证据，只读注释型） | ✅ |
| `MemorySettingsToggles.tsx` | 组件 | 记忆功能开关组（auto-save/recall 等） | ✅ |
| `MemoryStats.tsx` | 组件 | 记忆数量/类型统计摘要 | ✅ |
| `MemoryTabSwitcher.tsx` | 组件 | All/Pending/Archive Tab 切换 | ✅ |
| `MemoryTrashPanel.tsx` | 组件 | 已删除记忆回收站 | ✅ |
| `MemoryTypeIcon.tsx` | 辅助 | 记忆类型 → 图标映射 | ✅ |
| `PendingMemoryBadge.tsx` | 组件 | 待审批记忆计数徽章（ChatWindow 顶栏入口，pendingCount=0 时隐藏） | ✅ |
| `PendingMemoryDialog.tsx` | 组件 | 待审批记忆审批弹窗（支持编辑、批准、拒绝、来源跳转；连续审批：处理完自动显示下一条） | ✅ |
| `PendingMemoryList.tsx` | 组件 | 待审批记忆列表（含批量操作，用于 MemorySection pending tab） | ✅ |
| `__tests__/MemoryCommandCenterPanels.test.tsx` | 测试 | migration adapter missing 状态动作闭环与渲染守卫测试 | ✅ |

## 依赖

- `@/store/*`、`@/services/*`、`@/components/primitives/*`
- 父模块 [`features/_ARCH.md`](../_ARCH.md)
