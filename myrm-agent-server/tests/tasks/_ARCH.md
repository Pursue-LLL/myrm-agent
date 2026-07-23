# tests/tasks 模块架构

任务队列 server 侧行为测试目录，聚焦 `app/tasks/` 运行时语义（重试、状态迁移、事件发射）。

## 文件清单

| 文件 | 地位 | 职责 |
|------|------|------|
| `test_task_worker_retry.py` | 核心 | `TaskWorker` 自动重试行为回归：transient 重入 pending、permanent 失败终止、重试次数耗尽终止；验证 `next_retry_at` 未到期不消费、到期后可执行；验证自动重试清理 `error/result/worker*` 残留并记录 `metadata.last_error`；验证关键任务指标接线 |
| `test_task_event_bus.py` | 核心 | `TaskEventBus` 行为回归：正常事件入队；订阅队列满时有界淘汰最旧事件并投递带 `sync_required` 的最新事件；断言 emitted/dropped/replaced 指标计数与 queue_full warning 节流行为 |
