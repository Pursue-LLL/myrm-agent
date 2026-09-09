# chat-window/subagent/

Multi-agent execution tracking and visualization surfaces inside the chat window. State is managed by `@/store/chat/useSubagentStore`.

| File                                  | Responsibility                                                                                                            |
| ------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| `AgentWorkMap.tsx`                    | Topology and dependency graph visualization for subagents in execution                                                   |
| `ChatInlineTeamRunVisibilityStrip.tsx`| Compact inline execution summary strip displayed above the message composer                                              |
| `StageTaskCountStrip.tsx`             | Aggregated task counter strip grouped by execution stages                                                                  |
| `SubagentDashboard.tsx`               | Comprehensive multi-agent dashboard modal featuring Gantt chart, metrics strip, topology view, and budget controls       |
| `SubagentDetailDrawer.tsx`            | Detailed inspection drawer for individual subagent nodes, including overview, run journal, tools, messages, replay, and viewport |
| `SubagentGantt.tsx`                   | Horizontal timeline and duration Gantt chart for parallel subagent tasks                                                  |
| `SubagentInsightsView.tsx`            | Execution quality and performance insights breakdown (token consumption, duration, and error patterns)                    |
| `SubagentStream.tsx`                  | Live stream timeline component rendering subagent progress, thinking steps, and tool execution items                      |
| `SubagentTree.tsx`                    | Hierarchical tree view displaying parent-child subagent delegations and execution statuses                                |
| `SubagentViewportTab.tsx`             | Sandboxed browser live peek panel and terminal snapshot view with full-screen zoom and click-to-control desktop takeover    |

## Dependencies

- `@/store/chat/useSubagentStore` (POS: Multi-agent execution tree and stream state store)
- `@/store/useBrowserInspectorStore` (POS: Browser Inspector state management and scoped view data)
- `@/store/useChatStore` (POS: Active chat session identification)
- `@/lib/utils/subagentTree` (POS: Tree node calculations, formatting utilities, and cost extraction)
