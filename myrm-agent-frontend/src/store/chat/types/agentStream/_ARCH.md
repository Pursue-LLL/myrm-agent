# types/agentStream/

`AgentStreamEvent` 联合类型分片（控制 TypeScript 单文件体积）。

| 文件                                                     | 职责                                                                                                                                                                 |
| -------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `part1.ts` / `part2.ts` / `part2Catchup.ts` / `part3.ts` | 事件 payload 分片定义（`part2Catchup.ts` 为 catchup_snapshot 事件，含已登记的生成媒体 `media_generated`；含 `memory_brief`、`memory_brief_snapshot_id`、`memory_brief_status(source)` + `injection` 契约；`steering_unread` 载荷为回合自行结束时交还的、模型没读到的转向指令） |
| `union.ts`                                               | 合并为 `AgentStreamEvent` 导出                                                                                                                                       |

由 `types/index.ts` 再导出；SSE handler 与 `knownSseEventTypes` 消费。
