# hooks/tasks/

后台任务 SSE 订阅 hook 与门面导出。

| 文件 | 职责 |
|------|------|
| `useTasksSubscription.ts` | Chat 任务卡 SSE 订阅：经 `taskEventStream` 共享连接；按 `task_id` 拉取详情；`sync_required` 时节流全量自愈；断线时回退轮询 |
| `useMediaBackgroundTasks.ts` | BackgroundTasksPanel 媒体分区：活跃 + **近期 terminal** 任务；经 `taskEventStream` 共享 SSE 刷新 |
| `useGlobalMediaTaskNotifications.ts` | 媒体任务 terminal 通知（`enableWebNotifications` gate + chat 深链）；Tauri hidden 时 native notify，权限拒则 `requestUserAttention`；经 `taskEventStream` 共享 SSE |
| `index.ts` | 桶导出门面（白名单） |

## 依赖

- `@/services/mediaTasks`、`@/services/taskEventStream`、`@/services/notification`
- `@/store/useConfigStore`（通知偏好）
