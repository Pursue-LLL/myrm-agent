# hooks/tasks/

后台任务 WebSocket 订阅 hook 与门面导出。

| 文件 | 职责 |
|------|------|
| `useTasksSubscription.ts` | SSE 连接、按 `task_id` 拉取详情、断线时 `GET /api/v1/tasks?ids=...&detail=true` 回退轮询 |
| `index.ts` | 桶导出门面（白名单） |
