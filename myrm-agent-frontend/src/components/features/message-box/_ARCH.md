# message-box/

## 架构概述

消息气泡渲染：正文、思考链、进度条、来源与工具输出。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `ClarificationInput.tsx` | 组件/模块 | — | — |
| `ConsensusMetaDisplay.tsx` | 组件/模块 | — | — |
| `ContextUsageIndicator.tsx` | 组件/模块 | — | — |
| `CronJobSystemCard.tsx` | 组件/模块 | — | — |
| `FileMutationWarning.tsx` | 组件/模块 | — | — |
| `MarkdownContent.tsx` | 组件/模块 | — | — |
| `MemoryCitationsButton.tsx` | 组件/模块 | — | — |
| `MemoryInsightPanel.tsx` | 组件/模块 | — | — |
| `MessageActionBar.tsx` | 组件/模块 | — | — |
| `MessageBox.tsx` | 组件/模块 | — | — |
| `MessageBoxLoading.tsx` | 组件/模块 | — | — |
| `MessageSources.tsx` | 组件/模块 | — | — |
| `MessageToc.tsx` | 组件/模块 | — | — |
| `QuoteToolbar.tsx` | 组件/模块 | — | — |
| `Suggestions.tsx` | 组件/模块 | — | — |
| `TimeSlotPicker.tsx` | 组件/模块 | — | — |
| `TokenUsageDisplay.tsx` | 组件/模块 | — | — |
| `ToolCallApproval.tsx` | 组件/模块 | — | — |
| `ToolImageGallery.tsx` | 组件/模块 | — | — |
| `McpAppSection.tsx` | 组件/模块 | MCP Apps (ext-apps) embedded UI section — renders McpAppViewer for each MCP App view in a message | — |
| `UserMessage.tsx` | 组件/模块 | — | — |
| `WaterDropCostView.tsx` | 组件/模块 | — | — |
| `progress-steps/` | 目录 | 子模块 | — |
| `subagent/` | 目录 | 子模块 | — |

## 依赖

- `@/store/*`、`@/services/*`、`@/components/primitives/*`
- 父模块 [`features/_ARCH.md`](../_ARCH.md)
