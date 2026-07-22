# tests/tasks 模块架构

任务队列 server 侧行为测试目录，聚焦 `app/tasks/` 运行时语义（重试、状态迁移、事件发射）。

## 文件清单

| 文件 | 地位 | 职责 |
|------|------|------|
| `test_task_worker_retry.py` | 核心 | `TaskWorker` 自动重试行为回归：transient 重入 pending、permanent 失败终止、重试次数耗尽终止 |
