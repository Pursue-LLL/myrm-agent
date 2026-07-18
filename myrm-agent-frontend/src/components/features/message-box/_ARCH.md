# message-box/

## 架构概述

消息气泡渲染：正文、思考链、进度条、来源与工具输出。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `clarificationAnswer.ts` | 辅助 | 结构化澄清答案构建（questionId → optionId 契约） | ✅ |
| `ClarificationInput.tsx` | 组件 | 结构化澄清表单（多题/多选/开放题）；选项提交 `option.id`，展示 `label`；resume 与 legacy clarify API 双路径 | ✅ |
| `ConsensusMetaDisplay.tsx` | 组件 | MoA 元数据摘要 tooltip（模型数/聚合器/耗时） | ✅ |
| `ConsensusThinkingPanel.tsx` | 组件 | MoA 多模型思考面板：渐进式展示每个参考模型的状态、耗时、输出摘要（可折叠/展开） | ✅ |
| `ContextUsageIndicator.tsx` | 组件 | Token 用量环 + 策略状态点 + MiniPanel（压缩/Fork 新话题一键操作） | ✅ |
| `CronJobSystemCard.tsx` | 组件 | Cron 系统消息卡片（定时任务触发/结果摘要） | ✅ |
| `FileMutationWarning.tsx` | 组件 | 文件变更风险警告条（mutation 失败/冲突提示） | ✅ |
| `MarkdownContent.tsx` | 核心 | Markdown 渲染（数学公式/代码块/图表/GFM Alerts/脚注/citation），支持 web/mcp/kb/conversation 四种 citation 类型；KB citation 可点击打开 SourceChunkDrawer | ✅ |
| `MemoryCitationsButton.tsx` | 组件 | 记忆引用来源按钮与 Popover | ✅ |
| `MemoryInsightPanel.tsx` | 组件 | 消息关联记忆洞察侧栏（发送前 Memory Brief + 结束后 budget/citation + brief 降级可见提示）；`brief` 缺失时根据 `injection` 状态与 `not_applied` 原因映射可执行文案（已注入/未注入/工具模式/系统回退），并显式展示 `source=preflight/runtime_fallback` 语义；移动端额外渲染非 hover 的说明文案，避免触屏端诊断信息不可达 | ✅ |
| `PlanConfirmationCard.tsx` | 组件 | Plan-phase HITL 卡片：展示 AI 计划，提供批准/编辑/跳过三种操作。支持 Deep Research（PhaseWaiter REST）和 General Agent（LangGraph interrupt SSE resume）双路径 | ✅ |
| `WorkflowSuggestionCard.tsx` | 组件 | 非阻塞式 Workflow 建议内联卡片：检测到复杂可拆分任务时显示，提供 Enable（激活工作流模式）和 Dismiss（忽略）操作。不阻塞标准 Agent 流 | ✅ |
| `MessageActionBar.tsx` | 组件 | 消息操作栏：复制/朗读/Fork/记忆保存/技能提炼/Wiki保存等按钮 | ✅ |
| `MessageBox.tsx` | 核心 | 单条消息气泡根组件：路由 user/assistant/tool 分支 | ✅ |
| `MessageBoxLoading.tsx` | 辅助 | 流式生成中 assistant 气泡 loading 态 | ✅ |
| `MessageSources.tsx` | 组件 | 消息引用来源卡片网格（web/mcp/kb/conversation 四种类型差异化图标和 hover 预览）；KB 卡片点击打开 SourceChunkDrawer | ✅ |
| `SourceChunkDrawer.tsx` | 组件 | KB 引用原文片段 Drawer：点击 KB citation 后以右侧 Sheet 展示原文 snippet，支持 section 标签和分段渲染 | ✅ |
| `MessageToc.tsx` | 组件 | 长 assistant 消息目录导航（heading anchor） | ✅ |
| `QuoteToolbar.tsx` | 组件 | 文本选中引用工具条（Quote 回复） | ✅ |
| `Suggestions.tsx` | 组件 | 回合结束 follow-up 建议 chips | ✅ |
| `TokenUsageDisplay.tsx` | 组件 | Token 用量详情 tooltip：5 类 token 分类、费用、缓存命中率与节省、cache break 归因、模型/工具分解、TTFT/P95/TPS、会话基线对比、View Trace | ✅ |
| `ToolCallApproval.tsx` | 组件 | 消息内嵌工具审批请求卡片（非 visual 形态） | ✅ |
| `ToolImageGallery.tsx` | 组件 | MCP/工具图像画廊：base64+URL 双模式渲染、Lightbox 预览（箭头导航/键盘翻页/一键下载/计数器/标注编辑） | ✅ |
| `SessionRecordingCard.tsx` | 组件 | 会话录制视频回放卡片（HTML5 video player） | ✅ |
| `McpAppSection.tsx` | 组件 | MCP Apps (ext-apps) embedded UI section — renders McpAppViewer for each MCP App view in a message | ✅ |
| `UserMessage.tsx` | 核心 | 用户消息气泡：附件预览、编辑、重发 | ✅ |
| `WaterDropCostView.tsx` | 组件 | 消息内缓存节省 banner：cache hit ≥ 5% 时显示水滴图标 + 命中率 + 新 token 数 + 节省金额 | ✅ |
| `progress-steps/` | 目录 | Agent 进度步骤渲染与子 renderers | [_ARCH.md](progress-steps/_ARCH.md) |

## 依赖

- `@/store/*`、`@/services/*`、`@/components/primitives/*`
- 父模块 [`features/_ARCH.md`](../_ARCH.md)
