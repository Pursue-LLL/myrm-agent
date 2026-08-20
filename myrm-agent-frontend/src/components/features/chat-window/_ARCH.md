# chat-window/

## 架构概述

主对话窗口：消息列表、输入框、工具审批、Agent 配置、子代理与 Goal 控制面。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `AgentInfoBanner.tsx` | 组件 | 当前 Agent 信息横幅：头像+名称+描述+会话内切换下拉；设置快捷入口跳转 `/settings/wiki?agentId=` | ✅ |
| `BudgetBadge.tsx` | 组件 | 输入区旁会话/日预算用量微型进度指示（eco 模式叶标） | ✅ |
| `Chat.tsx` | 核心 | 消息列表容器：虚拟滚动阈值、JumpBar、审批 attention bar | ✅ |
| `ChatWindow.tsx` | 核心 | 主对话窗口入口：EmptyChat 与 Chat/ArtifactPortal 分轨 dynamic import；URL 深链 `restore_arg` / `approval`（Web Push 点击）；chips 行集成 `SessionRevertButton`（会话级文件 Undo）；`RunStatusChip` + `SessionAdvisorPanel`（Co-Pilot） | ✅ |
| `ChatWindowSatellites.tsx` | 核心 | 聊天窗口卫星组件：Browser/Desktop Inspector、PetOverlay/PetPalette（`companion_mode` gate）、SubagentDashboard 等 | ✅ |
| `ChatCronLink.tsx` | 组件 | 会话内关联定时任务 Badge（计数 → `/settings/cron?chat_id=`） | ✅ |
| `CompactedSummaryView.tsx` | 组件 | 上下文压缩摘要 + archive + 快照书签 list/fork（`forkContextBranch` + `router.push` 导航新会话，对齐 ForkDialog） | ✅ |
| `MigrationDiscoveryBanner.tsx` | 组件 | Local 空聊天页外部助手发现横幅；单源时深链 `?sub=migration&source=` | ✅ |
| `ConversationRecallHint.tsx` | 组件 | EmptyChat 历史会话搜索 opt-in 发现性横幅（Settings 深链） | ✅ |
| `ConversationJumpBar.tsx` | 组件 | 消息跳转条；Goal 侧栏 xl+ 时 `xl:right-[340px]` 避让 | ✅ |
| `DeleteChat.tsx` | 组件 | 删除当前会话按钮与确认流程 | ✅ |
| `EmptyChat.tsx` | 组件 | 空会话态：SamplePrompts + Companion + MessageInput + NoProviderBanner | ✅ |
| `NoProviderBanner.tsx` | 组件 | 未配置 AI Provider 时的引导横幅（amber 警告色），点击跳转 `/settings/models` | ✅ |
| `ForkButton.tsx` | 组件 | 触发 ForkDialog 的按钮（集成在 MessageActionBar、UserMessage 与 MessageInput 桌面工具栏） | ✅ |
| `ForkDialog.tsx` | 组件 | Fork 确认弹窗：标题输入 + 调 POST /fork + 自动导航 + streaming 防护 | ✅ |
| `RewindDialog.tsx` | 组件 | Rewind 确认弹窗：scope 选择（conversation/both）+ 文件变更预览（按 path 去重计数）+ POST /rewind + goal 暂停与文件恢复 toast 反馈 + composer 种子回填 | ✅ |
| `LifeStatusCapsule.tsx` | 组件 | Agent liveness 三态胶囊（busy/idle/degraded） | ✅ |
| `LinkDetectionDialog.tsx` | 组件 | 粘贴/发送外链前的安全确认对话框 | ✅ |
| `InputHistoryPopup.tsx` | 组件 | 输入历史弹窗列表（absolute 定位于输入框上方、ARIA listbox、Intl 相对时间 tooltip、click-outside 关闭） | ✅ |
| `MessageInput.tsx` | 核心 | 主输入框：附件、Slash、`@`/Tauri 侧栏 session drop→prior_chat cite、语音、模式切换、队列与流式发送；挂载 `WechatArticleComposerHint` | ✅ |
| `WechatArticleComposerHint.tsx` | 组件 | 输入区 banner：检测 `mp.weixin.qq.com/s/` 链接 → 引导挂载 `wechat-article-formatter` skill | ✅ |
| `wechatComposerHintUtils.ts` | 辅助 | 微信文章 URL 检测、formatter skill 挂载态判定、Agent 技能设置深链 | ✅ |
| `__tests__/wechatComposerHintUtils.test.ts` | 测试 | 微信文章 URL 检测与 formatter skill 挂载态 | ✅ |
| `WorkflowTemplateArmedBar.tsx` | 组件 | Composer pinned 模板武装条（显示名/ID + 取消固定） | ✅ |
| `SessionAccessRootsBar.tsx` | 组件 | 输入区上方 session 已授权目录 chips（RO/RW badge + 悬停全路径与一键复制 + revoke 撤销）；依赖 store `sessionAccessRoots`（grant 后 `sessionAccessRefresh` 刷新） | ✅ |
| `QueuedMessagesList.tsx` | 组件 | 消息队列可视化与 DnD 拖拽排序（复用 @dnd-kit 模式） | ✅ |
| `MessageListSkeleton.tsx` | 辅助 | 消息列表首屏加载 skeleton | ✅ |
| `ParentChatLink.tsx` | 组件 | 子会话返回父对话导航链接（集成在 ChatWindow） | ✅ |
| `LivenessIndicator.tsx` | 组件 | 聊天输入区 Agent 状态指示灯（6px 圆点，idle 隐藏，非 idle 显示颜色 + i18n tooltip；消费 useLivenessState 五态） | ✅ |
| `WorkingStateBadge.tsx` | 组件 | 对话头部工作记忆状态标识。有活跃 working state 时显示简洁的单行 badge | ✅ |
| `QuoteCard.tsx` | 组件 | 引用消息预览卡片（回复/转发上下文） | ✅ |
| `ReferenceMentionPopover.tsx` | 组件 | `@` 引用文件/记忆/会话的 Popover 选择器 | ✅ |
| `SamplePrompts.tsx` | 组件 | 空会话示例 prompt 芯片列表 | ✅ |
| `ScrollToBottomButton.tsx` | 组件/模块 | 滚动到底部浮动按钮（双态：↓ 箭头 / 新消息药丸） | ✅ |
| `YoloModeBanner.tsx` | 组件 | YOLO 模式全局警告横幅；org 全局 disableYolo 或 per-model MAP 约束时展示真实审批提示（ConfigSync + effective MAP SSE/visibility refetch + 当前 Agent 模型） | ✅ |
| `EStopBanner.tsx` | 组件/模块 | E-Stop 全局冻结横幅（GET /security/estop，解除冻结 POST resume） | ✅ |
| `ExtensionDisconnectedBanner.tsx` | 组件/模块 | Extension 断开警告横幅（条件性：仅 browserSource=extension 且未连接时显示，可 dismiss，SSE 驱动） | ✅ |
| `ExtensionTakeoverBanner.tsx` | 组件/模块 | 外部浏览器 HITL 横幅（harness `is_managed=false` → `uiMode=extension`：CDP/auto/extension 均 in-chat 引导本地 Chrome + Done/Skip；支持打开/复制签名远程接管链接；CAPTCHA auto_detect 时隐藏按钮） | ✅ |
| `SessionTrashPanel.tsx` | 组件 | 软删除会话回收站面板（恢复/永久删除） | ✅ |
| `AgentToolDiagnostics.tsx` | 组件 | Agent 工具健康诊断弹窗（tool 成功率/耗时） | ✅ |
| `SubagentPromptButton.tsx` | 组件 | 子代理 prompt 入口按钮（5s 倒计时自动 sendMessage） | ✅ |
| `ToolApprovalExpiryWatcher.tsx` | 组件/模块 | 工具审批过期 watcher（queue 过期 toast） | ✅ |
| `WorkspaceDirPicker.tsx` | 组件 | 工作目录选择器 Popover：路径直接输入+Enter导航、子目录过滤（>8项）、最近使用 LRU 5（localStorage）、Tauri 桌面端原生 OS picker（`@tauri-apps/plugin-dialog`）；Web/Cloud 走 Popover+Input，后端 `GET /browse` 零改动 | ✅ |
| `goals/` | 目录 | Goal 控制面与 DAG 可视化 | 见下表 |
| `mobile/` | 目录 | 移动端 Command Center 壳层与状态面板（MobileStatusBoard 等） | 见下表 |
| `catchup/` | 目录 | 会话 catch-up 摘要收件箱 UI（Companion SSE `catchup_snapshot` 消费） | 见 [catchup/_ARCH.md](catchup/_ARCH.md) |
| `virtual-message-list/` | 目录 | 虚拟化消息列表（`@tanstack/react-virtual` 高度缓存） | 见 [virtual-message-list/_ARCH.md](virtual-message-list/_ARCH.md) |

## agent-config-panel/

详见 [agent-config-panel/_ARCH.md](agent-config-panel/_ARCH.md)。内置工具 ID 与 server `resolve_builtin_tool_flags()` 必须同步（含 `render_ui`）。

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `AgentConfigPanel.tsx` | 核心 | Agent 配置面板入口 | ✅ |
| `AgentConfigEditDialog.tsx` | 核心 | Agent 配置编辑弹窗（skills/MCP/指令/内置工具/subagents） | ✅ |
| `AgentConfigSelectableCard.tsx` | 辅助 | 可勾选配置卡片与「添加更多」按钮 | ✅ |
| `ActionSpaceAccuracyRadar.tsx` | 辅助 | 动作空间准确度预测条与沉睡技能净化提示 | ✅ |
| `TemplateMarket.tsx` | 核心 | Agent 模板市场。请求后端的 `/api/v1/agents/templates` 和 `instantiate-template` 接口，实现模板列表展示和带有原子化依赖预检的智能体实例化。 | ✅ |
| `AgentGallery.tsx` | 辅助 | Agent 画廊展示 | ✅ |

## subagent/

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `SubagentDashboard.tsx` | 核心 | 子代理控制面板入口：两视图 tab（树/画布）；树视图内排序/过滤条（`subagent-sort-*`/`subagent-filter-*`）、MiniGantt、fission 摘要条（`subagent-fission-summary`）、头部汇总、预算 token/cost（`extractBudgetTokens`/`extractMaxCostUsd`）、取消全部/委托暂停、overtime/stale 汇总态、画布 tab 挂载 `AgentWorkMap`，画布节点点击切树视图定位（`data-subagent-tree-id`）；SSE `subagents_updated`/`teammate_message` 消费 + 轮询拉取；面板/触发器 `data-testid` 供 E2E 选择 | ✅ |
| `AgentWorkMap.tsx` | 组件 | 长任务拓扑画布（Task Tray「画布」tab）：ReactFlow+dagre 渲染 subagent 树/fission 拓扑（merge 并行）；结构/数据双 effect（节点增删才重排，实时进度更新保留拖拽坐标）；结构变化 fitView 平滑跟随；节点点击回调（画布→树定位桥接）；移动端紧凑节点+窄屏隐藏 MiniMap；墓碑（failed/cancelled 红高亮+error）、焦点（running 脉冲）、进度条、cost/tokens/耗时元数据、空态；验证失败节点 tone 红化 + `verificationFailed` 徽章（执行完成≠事实可信双轨语义）；数据源 `taskTopologyModel` | ✅ |
| `SubagentTree.tsx` | 组件 | 子代理树视图：`SubagentTreeNode` 递归节点（展开/折叠、状态图标、cost/tokens/model/进度/耗时、验证徽章 `subagent-verification-badge`（PASS/FAIL + findings 展开）、steer/cancel/重新发起/审批跳转、overtime/stale 告警、teammate 消息、stream、取消确认弹窗）+ 聚合徽章 + role/scope 格式化；依赖 `SubagentStream` | ✅ |
| `SubagentGantt.tsx` | 组件 | 子代理迷你甘特图：基于 startedAt/duration 的并行时间条（状态色条、相对缩放），少于 2 个时间跨度的节点时隐藏；折叠开关 `subagent-gantt-toggle`、容器 `subagent-gantt` 供 E2E 选择 | ✅ |
| `SubagentStream.tsx` | 组件 | 子代理状态图标（12 态 STATUS_ICON_MAP）与实时流条目展示（NodeStream/StreamLine：tool/progress/thinking/error 字形 + 耗时 + 滚动跟随） | ✅ |

## goals/

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `GoalControlPlane.tsx` | 核心 | Goal 运行时 todo 侧栏（xl+ 显示；移动端用聊天气泡 ProgressSteps） | ✅ |
| `GoalQueueSection.tsx` | 核心 | Goal 队列区块 | ✅ |
| `GoalStatusCard.tsx` | 核心 | 单 Goal 状态卡片 | ✅ |
| `goal-icons.tsx` | 辅助 | Goal 图标集 | ✅ |

## mobile/

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `MobileActionSheet.tsx` | 组件 | 移动端底部动作 Sheet（`useMobileSheetEntries` 驱动） | ✅ |
| `MobileStatusBoard.tsx` | 核心 | 移动端 Command Center 壳层（审批/预览/进度/快捷输入 + Co-Pilot chip/Advisor；run 中「查看完整对话」→ 主 Chat 复用 QuoteToolbar 划词） | ✅ |
| `MobileStatusApprovalsSection.tsx` | 组件 | 移动端待审批队列区块 | ✅ |
| `MobileStatusLivePreview.tsx` | 组件 | 浏览器/桌面 Live Preview 与 Lightbox | ✅ |
| `MobileStatusMessageBody.tsx` | 组件 | 进度/验证/思考/结果/Artifact 交付物列表与 Plan 步骤；run 结束后 result 卡片「查看完整对话」跳转主 Chat | ✅ |
| `useMobileSheetEntries.tsx` | 辅助 | 移动端动作 Sheet 条目 hook | ✅ |

## Visual Approval（工具 HITL 截图审批）

## copilot/

详见 [copilot/_ARCH.md](../copilot/_ARCH.md)。`RunStatusChip` + `SessionAdvisorPanel` 由 `ChatWindow` / `MobileStatusBoard` 挂载。

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `VisualApprovalInlineSection.tsx` | 入口 | 消息级 inline 审批挂载 | ✅ |
| `VisualApprovalArtifactCard.tsx` | UI | 截图 BBox + 操作区 | ✅ |
| `VisualApprovalPendingCard.tsx` | UI | snapshot loading | ✅ |
| `approval/VisualApprovalRequestRenderer.tsx` | UI | 三态路由 | ✅ |
| `approval/VisualApprovalUnavailableCard.tsx` | UI | 失败降级 + 重试 | ✅ |
| `approval/VisualApprovalHighlight.tsx` | UI | 红框 overlay | ✅ |
| `VisualApprovalOsOverlaySync.tsx` | UI | Tauri OS overlay 同步 | ✅ |
| `VisualApprovalAttentionBar.tsx` | UI | 滚动区外 pending 可达条 | ✅ |
| `approval/ShellCommandDisplay.tsx` | UI | shell 命令终端展示 + span 高亮 + unknown 段 risk reason tooltip | ✅ |
| `approval/AllowAlwaysConfirmDialog.tsx` | UI | allow-always 范围选择；pattern 无法推导时禁用 Confirm | ✅ |
| `SingleApprovalCard.tsx` | UI | 主 Agent 单条/批量审批（shell edit 经 mergeShellEditedArgs） | ✅ |
| `ToolApprovalDialog.tsx` | UI | modal 非 visual 审批 | ✅ |
| `MobileStatusBoard.tsx` | UI | 移动端审批面板 | ✅ |

逻辑层见 [`lib/approval/_ARCH.md`](../../lib/approval/_ARCH.md)。

## 依赖

- `@/store/*`、`@/services/*`、`@/components/primitives/*`
- `@/lib/e2ee/useE2EEStatus` — MobileStatusBoard E2EE 状态
- `@/components/features/e2ee/E2EESecurityPanel` — MobileStatusBoard E2EE badge
- 父模块 [`features/_ARCH.md`](../_ARCH.md)
