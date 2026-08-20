# memory/

## 架构概述

记忆中心：浏览、编辑、归档与召回相关 UI。

组件按功能域收进子目录，根目录仅保留本架构文档与 `__tests__/`：

| 子目录            | 职责                                                                             |
| ----------------- | -------------------------------------------------------------------------------- |
| `cards/`          | 单条记忆卡片与展示件（MemoryCard/ConflictCard/TypeIcon/Stats/详情 Sheet/摘要卡） |
| `command-center/` | 记忆命令中心（主布局/高级面板/Chrome/Doctor 诊断/主内容区面板编排）              |
| `dialogs/`        | 记忆相关对话框（创建/编辑/清空/归档恢复/导入审阅/共享规则/Connect Wizard）       |
| `guides/`         | 引导与说明卡（首次引导/分层说明）                                                |
| `hooks/`          | 记忆域自定义 hooks（归档恢复动作/Demo 种子）                                     |
| `insights/`       | 洞察展示（健康仪表盘/知识图谱/Shared Context 编辑预览）                          |
| `pending/`        | 待审批记忆（计数徽章/审批弹窗/批量列表）                                         |
| `replay/`         | 会话回放（回放器/消息气泡/召回面板/实时流/时间线工具）                           |
| `settings/`       | 设置区（功能开关/Tab 切换/回收站）                                               |
| `shared-context/` | 共享上下文（面板/目标绑定/健康横幅/面板 hook）                                   |

## 文件清单

### cards/

| 文件                          | 地位 | 职责                                                                                    | I/O/P |
| ----------------------------- | ---- | --------------------------------------------------------------------------------------- | ----- |
| `MemoryCard.tsx`              | 核心 | 单条记忆卡片（类型/icon/摘要/操作菜单；procedural 规则 TTL 显示，用户锁定隐藏过期天数） | ✅    |
| `ConflictCard.tsx`            | 组件 | 冲突记忆卡                                                                              | ✅    |
| `MemoryDetailSheet.tsx`       | 组件 | 记忆详情 Sheet（全文/metadata/来源）                                                    | ✅    |
| `MemoryTypeIcon.tsx`          | 辅助 | 记忆类型 → 图标映射                                                                     | ✅    |
| `MemoryStats.tsx`             | 组件 | 记忆数量/类型统计摘要                                                                   | ✅    |
| `PreferenceStabilityCard.tsx` | 组件 | 偏好稳定性卡                                                                            | ✅    |
| `TasteSummaryCard.tsx`        | 组件 | 口味摘要卡                                                                              | ✅    |

### command-center/

| 文件                                    | 地位 | 职责                                                                                                                                                                                                     | I/O/P |
| --------------------------------------- | ---- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----- |
| `MemoryCommandCenter.tsx`               | 核心 | 记忆命令中心主布局入口；消费 migration manifest authoritative 语义并驱动向导深链；支持通过 URL `?project=` 或下拉筛选器按项目过滤 SharedContext 记忆空间                                                 | ✅    |
| `MemoryCommandCenterAdvancedPanels.tsx` | 组件 | 高级面板：导入/导出/图谱/Doctor                                                                                                                                                                          | ✅    |
| `MemoryCommandCenterChrome.tsx`         | 组件 | 命令中心顶栏、Tab 与搜索框                                                                                                                                                                               | ✅    |
| `MemoryCommandCenterDoctorPanel.tsx`    | 组件 | 记忆系统 Doctor 诊断面板；含静态检查、可执行诊断、结构化 benchmark 指标卡片与历史趋势（最近 N 次 recall@5/ndcg@5/mrr/latency p50/p95 + 上次 delta + 类别通过率 + run 状态徽章 + embedding 模型漂移提示） | ✅    |
| `MemoryCommandCenterPanels.tsx`         | 组件 | 主内容区 Tab 面板编排（含 migration 最近导入 batch 的执行就绪/首轮 outcome 展示、adapter readiness 可视化与 missing 状态迁移向导动作闭环）                                                               | ✅    |

### dialogs/

| 文件                             | 地位 | 职责                                                                                                                                                                                                      | I/O/P |
| -------------------------------- | ---- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----- |
| `ConnectWizardDialog.tsx`        | 组件 | 外部 AI 工具 Connect Wizard：Myrm Agent Profile 选择器 + 外部工具 profile 选择 → 生成 MCP 配置（token 携带 agent_id 作用域）→ Agent Plugins bundle 生成/逐文件与整体 zip 下载 → doctor 验证 → revoke 管理 | ✅    |
| `MemoryArchiveRestoreDialog.tsx` | 组件 | 记忆归档批量恢复确认对话框                                                                                                                                                                                | ✅    |
| `MemoryClearAllDialog.tsx`       | 组件 | 清空全部记忆二次确认                                                                                                                                                                                      | ✅    |
| `MemoryCreateDialog.tsx`         | 组件 | 手动创建记忆对话框                                                                                                                                                                                        | ✅    |
| `MemoryEditDialog.tsx`           | 组件 | 编辑记忆内容与标签                                                                                                                                                                                        | ✅    |
| `MemoryImportReviewDialog.tsx`   | 组件 | 批量导入 dry-run 结果审阅                                                                                                                                                                                 | ✅    |
| `ShareRulesDialog.tsx`           | 组件 | 共享规则对话框                                                                                                                                                                                            | ✅    |

### guides/

| 文件                   | 地位 | 职责                                                                           | I/O/P |
| ---------------------- | ---- | ------------------------------------------------------------------------------ | ----- |
| `MemoryGuide.tsx`      | 组件 | 首次使用记忆功能引导                                                           | ✅    |
| `MemoryLayerGuide.tsx` | 组件 | Command Center 记忆分层说明卡（工作集/任务状态/长期记忆/原始证据，只读注释型） | ✅    |

### hooks/

| 文件                                | 地位 | 职责                   | I/O/P |
| ----------------------------------- | ---- | ---------------------- | ----- |
| `useMemoryArchiveRestoreActions.ts` | 辅助 | 记忆归档恢复动作 hooks | ✅    |
| `useMemoryDemoSeed.ts`              | 辅助 | Demo 种子数据 hooks    | ✅    |

### insights/

| 文件                        | 地位 | 职责                            | I/O/P |
| --------------------------- | ---- | ------------------------------- | ----- |
| `MemoryContextPanel.tsx`    | 组件 | Shared Context 编辑与预览       | ✅    |
| `MemoryHealthDashboard.tsx` | 组件 | 记忆健康度指标仪表盘            | ✅    |
| `MemoryKnowledgeGraph.tsx`  | 组件 | 记忆知识图谱 force-graph 可视化 | ✅    |

### pending/

| 文件                      | 地位 | 职责                                                                                                                               | I/O/P |
| ------------------------- | ---- | ---------------------------------------------------------------------------------------------------------------------------------- | ----- |
| `PendingMemoryBadge.tsx`  | 组件 | 待审批记忆计数徽章（ChatWindow 顶栏入口，待审批与冲突总数均为 0 时隐藏；纯展示，新冲突通知由全局 memory_operation SSE toast 承担） | ✅    |
| `PendingMemoryDialog.tsx` | 组件 | 待审批记忆审批弹窗（支持编辑、批准、拒绝、来源跳转；连续审批：处理完自动显示下一条）                                               | ✅    |
| `PendingMemoryList.tsx`   | 组件 | 待审批记忆列表（含批量操作，用于 MemorySection pending tab）                                                                       | ✅    |

### replay/

| 文件                          | 地位 | 职责                                                                   | I/O/P |
| ----------------------------- | ---- | ---------------------------------------------------------------------- | ----- |
| `ConversationRecallPanel.tsx` | 组件 | 历史会话召回搜索与插入面板                                             | ✅    |
| `ReplayControls.tsx`          | 组件 | 回放控制条（标题/跳错/速度/播放暂停/带事件标记的进度条）               | ✅    |
| `ReplayInspector.tsx`         | 组件 | 回放明细检查器（当前时间线事件的错误/工具结果/安全标签/LLM 统计）      | ✅    |
| `ReplayMessageBubble.tsx`     | 组件 | 回放消息气泡                                                           | ✅    |
| `ReplayMindView.tsx`          | 组件 | 回放脑图面板（LLM 调用/记忆事件/人工反馈/推理轨迹/带安全徽标的工具行） | ✅    |
| `SessionReplayPlayer.tsx`     | 组件 | 会话回放播放器（编排 Controls/MindView/Inspector 三栏）                | ✅    |
| `memoryLiveStream.ts`         | 工具 | 记忆实时流事件解析与 replay session 解析                               | ✅    |
| `replayTimeline.ts`           | 工具 | 回放时间线构建                                                         | ✅    |

### settings/

| 文件                        | 地位 | 职责                                  | I/O/P |
| --------------------------- | ---- | ------------------------------------- | ----- |
| `MemorySettingsToggles.tsx` | 组件 | 记忆功能开关组（auto-save/recall 等） | ✅    |
| `MemoryTabSwitcher.tsx`     | 组件 | All/Pending/Archive Tab 切换          | ✅    |
| `MemoryTrashPanel.tsx`      | 组件 | 已删除记忆回收站                      | ✅    |

### shared-context/

| 文件                                  | 地位 | 职责                     | I/O/P |
| ------------------------------------- | ---- | ------------------------ | ----- |
| `SharedContextPanel.tsx`              | 组件 | 共享上下文面板           | ✅    |
| `SharedContextTargetBinding.tsx`      | 组件 | 共享上下文目标绑定       | ✅    |
| `SharedContextMemoryHealthBanner.tsx` | 组件 | 共享上下文健康横幅       | ✅    |
| `useSharedContextPanel.ts`            | 辅助 | 共享上下文面板状态 hooks | ✅    |

### 测试

| 文件                                                | 职责                                                                         | I/O/P |
| --------------------------------------------------- | ---------------------------------------------------------------------------- | ----- |
| `__tests__/MemoryCommandCenterDoctorPanel.test.tsx` | Doctor 诊断面板渲染与健康指标卡测试                                          | ✅    |
| `__tests__/MemoryCommandCenterPanels.test.tsx`      | migration adapter missing 状态动作闭环与渲染守卫测试                         | ✅    |
| `__tests__/MemoryCard.ttl.test.tsx`                 | procedural 卡片 TTL 显示：未锁定显示过期天数、用户锁定（is_user_locked）隐藏 | ✅    |
| `__tests__/PendingMemoryList.test.tsx`              | 待审批记忆列表批量操作测试                                                   | ✅    |
| `__tests__/SharedContextPanel.test.tsx`             | 共享上下文面板测试                                                           | ✅    |
| `__tests__/SharedContextTargetBinding.test.tsx`     | 共享上下文目标绑定测试                                                       | ✅    |
| `__tests__/memoryLiveStream.test.ts`                | 记忆实时流测试                                                               | ✅    |
| `__tests__/replayTimeline.test.ts`                  | 记忆回放时间线测试                                                           | ✅    |
| `__tests__/SessionReplayPlayer.test.tsx`            | 回放播放器安全徽标渲染与 store selector 稳定性测试                           | ✅    |

## 依赖

- `@/store/*`、`@/services/*`、`@/components/primitives/*`
- 父模块 [`features/_ARCH.md`](../_ARCH.md)

## 引用规范

- 域内跨子目录引用一律用相对路径（如 `../cards/MemoryTypeIcon`），禁止经目录级 `index.ts` 桶文件聚合，避免循环依赖与 tree-shaking 损伤。
- 外部模块消费 memory 组件一律直连子目录路径（如 `@/components/features/memory/cards/MemoryCard`）；禁止在子目录中新增 `index.ts` 桶文件。
