# types/agentStream/

`AgentStreamEvent` 联合类型分片（控制 TypeScript 单文件体积）。

| 文件 | 职责 |
|------|------|
| `part1.ts` / `part2.ts` / `part3.ts` | 事件 payload 分片定义（含 `memory_brief`、`memory_brief_snapshot_id`、`memory_brief_status` 契约） |
| `union.ts` | 合并为 `AgentStreamEvent` 导出 |

由 `types/index.ts` 再导出；SSE handler 与 `knownSseEventTypes` 消费。
