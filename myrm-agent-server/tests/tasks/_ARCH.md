# tests/tasks 模块架构

任务队列 server 侧行为测试目录，聚焦 `app/tasks/` 运行时语义（并发上限、队列顺序、终态只写一次、取消与重启恢复、事件发射）。

## 文件清单

| 文件 | 地位 | 职责 |
|------|------|------|
| `test_task_worker.py` | 核心 | `TaskWorker` 真实 SQLiteTaskStore + 脚本化 executor：成功/失败分类（transient/permanent）不重入队、超时永久失败、无 executor 失败；优先级再先进先出；并发上限不被突破；一个 run 结束即补位不等最慢任务；`abort` 中止在途 run 且保持 `cancelled`；迟到结果不覆盖 `cancelled`；已取消的排队任务不被认领；启动时遗留 `running` 置 `interrupted`（transient）；`stop()` 把在途任务标记 `interrupted`；成功/失败/超时指标接线 |
| `test_task_event_bus.py` | 核心 | `TaskEventBus` 行为回归：正常事件入队；订阅队列满时有界淘汰最旧事件并投递带 `sync_required` 的最新事件；断言 emitted/dropped/replaced 指标计数与 queue_full warning 节流行为 |
