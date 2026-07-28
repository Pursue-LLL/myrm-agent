# hooks/workspace/

工作区与 artifact 相关流式/存储 hook。

| 文件 | 职责 |
|------|------|
| `useWorkspaceStream.ts` | 工作区文件流 |
| `useWidgetStorage.ts` | Widget iframe localStorage 桥接 |
| `useArtifactVersionsFromHistory.ts` | 从历史解析 artifact 版本 |
| `useBatchWebSocket.ts` | 批量 WebSocket |

消费者：`project-workspace/`、artifacts、workspace-browser。
