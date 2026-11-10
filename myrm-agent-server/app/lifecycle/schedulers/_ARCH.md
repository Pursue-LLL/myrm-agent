# app/lifecycle/schedulers 子包架构

进程生命周期里的后台调度器。按被调度的对象分模块，`__init__.py` 聚合全部 start/stop 钩子，`app.lifecycle.schedulers` 导入路径不变。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 子域出口 | 聚合 re-export 全部 `start_*` / `stop_*` 与 job 函数（测试与 lifespan 共用） | — |
| `common.py` | 辅助 | 共享 logger 与 monitor 批量常量（冷启动清洗批次） | ✅ |
| `cron.py` | 核心 | Cron Scheduler 启动 | ✅ |
| `context.py` | 核心 | 上下文文件每日清理 + 三个遥测 dispatcher（压缩 / memory brief / guardian）起停 | ✅ |
| `maintenance.py` | 核心 | 数据库维护（6 小时）：WAL、共享库 GC、浏览器会话 GC、无痕清理、checkpoint 裁剪、实例备份；含 monitor 批量清洗 | ✅ |
| `security.py` | 核心 | 审批 TTL、取消令牌、登录会话、认证日志清理 | ✅ |
| `kanban.py` | 核心 | Kanban 派发准备（`prepare_kanban_dispatch`：Boot Recovery + runner/specifier/decomposer，HTTP bind 之前）、dispatcher 后台启动（`start_kanban_dispatchers`：bind 之后延后 `BOOT_DISPATCH_DELAY_SECONDS`）与停止 | ✅ |
| `backup.py` | 核心 | 远程记忆备份的小时级检查 | ✅ |

## 依赖关系

- 上游：`app.core.infra.background_task`、APScheduler、各业务服务（清理 / 备份 / 遥测）
- 下游：`app/server/lifespan/`（起停编排）、`tests/lifecycle/*`
