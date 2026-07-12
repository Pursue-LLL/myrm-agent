# hooks/tasks/

后台任务 WebSocket 订阅 hook 与门面导出。

| 文件 | 职责 |
|------|------|
| `useTasksSubscription.ts` | WS 连接、任务事件写入 `store/tasks` |
| `index.ts` | 桶导出门面（白名单） |
