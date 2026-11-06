# app/server/lifespan 子包架构

FastAPI 应用 lifespan。启动按“串行关键阶段 → 并行阶段”执行，关闭时逆序收尾；`optimized_lifespan` 只做编排，阶段实现分模块。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 子域出口 | 聚合 `optimized_lifespan`、阶段函数与 logger（测试用 `inspect` 检查阶段实现） | — |
| `state.py` | 辅助 | logger、`_checkpointer_cleanup` 与 `_context_cleanup_scheduler_instance` 两个进程级句柄 | ✅ |
| `startup.py` | 核心 | `_phase_1a_sequential`（配置迁移、checkpointer、隐私策略、自动续跑等）、`_phase_1b_parallel`（并行启动任务与严格配对的日志标签）及启动小工具（pool metrics、@startup 事件、工具层预热、trunk 模板、code execution 配置） | ✅ |
| `shutdown.py` | 核心 | `_shutdown`：定时器、scheduler、checkpointer、数据库连接的逆序关闭 | ✅ |
| `app.py` | 核心 | `optimized_lifespan`：环境重置 → 串行阶段 → 并行阶段 → 就绪 → 关闭编排 | ✅ |

## 依赖关系

- 上游：`app.config.settings`、`app.lifecycle`、`app.server.warmup`、harness `StartupTimer`
- 下游：`app/main.py`（挂载 lifespan）
