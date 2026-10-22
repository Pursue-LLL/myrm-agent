# chat-window/subagent/

Multi-agent execution tracking and visualization surfaces inside the chat window. State is managed by `@/store/chat/useSubagentStore`.

| File                                   | Responsibility                                                                                                                                                                                      |
| -------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `AgentWorkMap.tsx`                     | Topology and dependency graph visualization for subagents in execution                                                                                                                              |
| `ChatInlineTeamRunVisibilityStrip.tsx` | Compact inline execution summary strip displayed above the message composer                                                                                                                         |
| `StageTaskCountStrip.tsx`              | Aggregated task counter strip grouped by execution stages                                                                                                                                           |
| `SubagentDashboard.tsx`                | Comprehensive multi-agent dashboard modal featuring Gantt chart, metrics strip, topology view, and budget controls                                                                                  |
| `SubagentDetailDrawer.tsx`             | Detailed inspection drawer shell for individual subagent nodes: header, metrics strip, keyboard-navigable tab navigation (Radix Tabs), and the run journal, tools, messages, and replay tabs        |
| `SubagentOverviewTab.tsx`              | Overview tab of the detail drawer: handover report, failure notice, verification verdict, task spec, and node metadata with local copy actions                                                      |
| `SubagentViewportTab.tsx`              | Viewport tab of the detail drawer: sandboxed browser live peek, lightboxed zoom, and terminal snapshot for the node                                                                                 |
| `SubagentErrorNotice.tsx`              | Failure panel of the detail drawer: raw error text for failed nodes, a localized "needs review" note (amber) for blocked nodes whose verification reached no conclusion                             |
| `SubagentGantt.tsx`                    | Horizontal timeline and duration Gantt chart for parallel subagent tasks                                                                                                                            |
| `SubagentInsightsView.tsx`             | Execution quality and performance insights breakdown (token consumption, duration, and error patterns)                                                                                              |
| `SubagentRoleChainPresetChips.tsx`     | Golden role chain preset chips bar with review-loop bounds and Article 55 DoD guards (implement-review-fix, watchdog, editorial)                                                                    |
| `SubagentStream.tsx`                   | Live stream timeline component rendering subagent progress, thinking steps, and tool execution items                                                                                                |
| `SubagentTree.tsx`                     | Hierarchical tree view displaying parent-child subagent delegations and execution statuses; a steer refused by the risk gate (`risk_held`) is shown through the shared localized notice, not a raw error                                                                                                          |
| `AgentMultiplexerPanel.tsx`            | Persistent tmux-style Agent Session Multiplexer workbench for slicing across concurrent sessions, inspecting logs/artifacts, and injecting steering instructions                                    |
| `AgentHubSupervisionDrawer.tsx`        | 子代理实时监管抽屉组件（Alt+A 快捷键唤起）：呈现 Roster 全景与状态机（running/parked/stuck/done）、单 Worker Live Transcript 实时流、以及 Steer 纠偏/Kill stuck 终止/Revive parked 唤醒三大干预控制 |

## Dependencies

- `@/store/chat/useSubagentStore` (POS: Multi-agent execution tree and stream state store)
- `@/store/useBrowserInspectorStore` (POS: Browser Inspector state management and scoped view data)
- `@/store/useChatStore` (POS: Active chat session identification)
- `@/lib/utils/subagentTree` (POS: Tree node calculations, formatting utilities, and cost extraction)
