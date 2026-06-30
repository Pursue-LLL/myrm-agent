# message-box/

## 架构概述

消息气泡渲染：正文、思考链、进度条、来源与工具输出。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `ClarificationInput.tsx` | 组件/模块 | — | — |
| `ConsensusMetaDisplay.tsx` | 组件/模块 | MoA 元数据摘要 tooltip（模型数/聚合器/耗时） | ✅ |
| `ConsensusThinkingPanel.tsx` | 组件 | MoA 多模型思考面板：渐进式展示每个参考模型的状态、耗时、输出摘要（可折叠/展开） | ✅ |
| `ContextUsageIndicator.tsx` | 组件/模块 | — | — |
| `CronJobSystemCard.tsx` | 组件/模块 | — | — |
| `FileMutationWarning.tsx` | 组件/模块 | — | — |
| `MarkdownContent.tsx` | 组件/模块 | Markdown 渲染（数学公式/代码块/图表/GFM Alerts/脚注/citation），支持 web/mcp/kb/conversation 四种 citation 类型 | ✅ |
| `MemoryCitationsButton.tsx` | 组件/模块 | — | — |
| `MemoryInsightPanel.tsx` | 组件/模块 | — | — |
| `MessageActionBar.tsx` | 组件 | 消息操作栏：复制/朗读/Fork/Wiki保存等按钮 | ✅ |
| `MessageBox.tsx` | 组件/模块 | — | — |
| `MessageBoxLoading.tsx` | 组件/模块 | — | — |
| `MessageSources.tsx` | 组件/模块 | 消息引用来源卡片网格（web/mcp/kb/conversation 四种类型差异化图标和 hover 预览） | ✅ |
| `MessageToc.tsx` | 组件/模块 | — | — |
| `QuoteToolbar.tsx` | 组件/模块 | — | — |
| `Suggestions.tsx` | 组件/模块 | — | — |
| `TokenUsageDisplay.tsx` | 组件 | Token 用量详情 tooltip：5 类 token 分类、费用、缓存命中率与节省、cache break 归因、模型/工具分解、TTFT/P95/TPS、会话基线对比、View Trace | ✅ |
| `ToolCallApproval.tsx` | 组件/模块 | — | — |
| `ToolImageGallery.tsx` | 组件 | MCP/工具图像画廊：base64+URL 双模式渲染、Lightbox 预览（箭头导航/键盘翻页/一键下载/计数器/标注编辑） | ✅ |
| `SessionRecordingCard.tsx` | 组件/模块 | 会话录制视频回放卡片（HTML5 video player） | ✅ |
| `McpAppSection.tsx` | 组件/模块 | MCP Apps (ext-apps) embedded UI section — renders McpAppViewer for each MCP App view in a message | — |
| `UserMessage.tsx` | 组件/模块 | — | — |
| `WaterDropCostView.tsx` | 组件 | 消息内缓存节省 banner：cache hit ≥ 5% 时显示水滴图标 + 命中率 + 新 token 数 + 节省金额 | ✅ |
| `progress-steps/` | 目录 | 子模块 | — |
| `subagent/` | 目录 | 子模块 | — |

## 依赖

- `@/store/*`、`@/services/*`、`@/components/primitives/*`
- 父模块 [`features/_ARCH.md`](../_ARCH.md)
