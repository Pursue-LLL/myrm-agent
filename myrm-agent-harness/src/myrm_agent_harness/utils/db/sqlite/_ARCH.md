# db/sqlite/

## 架构概述
统一的 SQLite 硬化工厂：每个 store 通过它打开连接，获得一致的持久化 / 隐私 /
并发 / 崩溃恢复保障（声明式 Profile + 连接硬化 + 文件级完整性守卫）。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 门面 | 对外导出 Profile 预设、连接硬化、完整性原语与 SchemaGate | ✅ |
| `profile.py` | 配置 | 冻结的 `SQLiteProfile` PRAGMA 规格与五档预设（`DEFAULT`/`DURABLE`/`SENSITIVE`/`CACHE`/`READONLY`） | ✅ |
| `integrity.py` | 叶子 | 文件级守卫与崩溃恢复：header magic 校验、`page_count` 截断不变量、孤儿 WAL 清理、有界 `quick_check_sync`、WAL `checkpoint_truncate`、`incremental_vacuum`、`prepare_database_file` | ✅ |
| `schema_gate.py` | 叶子 | 存储能力契约 `StorageCapabilities` 与 Fail-Closed 启动门禁：`PRAGMA user_version` 防降级破坏、结构完整性校验 | ✅ |
| `hardening.py` | 核心 | `harden_connection_sync/async`（应用 Profile 与可选能力门禁，返回 journal 模式）、`connect_async` 上下文管理器（短连接）、`open_hardened_async`（长连接：连接 → 加固 → 调用方的 `prepare` 建表或迁移 → 返回；任一步失败或被取消都先关闭连接再重新抛出，持有者拿到的要么是完整连接，要么什么都没有）、`RollbackBeforeCloseConnection`（上面两种连接用的连接类：关闭前先回滚）、`should_fallback_to_delete`（WAL→DELETE 降级的唯一决策真源） | ✅ |

## 模块依赖
- `hardening.py` → `profile.py`、`integrity.py`（叶子，无内部反向依赖）
- 消费方：harness 内全部 SQLite store；业务层 `myrm-agent-server/app/database/factory.py`
  的 SQLAlchemy 监听复用 `should_fallback_to_delete`，使主库共享同一 EIO 安全回退契约；同一文件创建的引擎也用
  `RollbackBeforeCloseConnection` 作连接类，使主库与 harness 的 store 共享同一“关闭不留写锁”契约。

## 关键契约
- **EIO 安全回退**：仅当错误确定性地表明文件系统不支持 WAL 时才永久降级为 DELETE；
  当 on-disk header 证明数据库已是 WAL 时绝不降级（瞬时 I/O 错误保持 WAL）。
- **长连接不留半成品**：懒打开连接的 store 经 `open_hardened_async` 在自己的锁里打开，成功后才保存；打开失败或被取消时连接已被关闭，下一次调用从头再来。`close()` 拿同一把锁，与打开重叠的关闭会等它结束。
- **关闭不留写锁**：`connect_async` 与 `open_hardened_async` 的连接类是 `RollbackBeforeCloseConnection`，`close()` 先回滚再关闭。任务在语句执行与 `RETURNING` 取行之间被取消时，连接上还留着一条未完成的语句，而 SQLite 的 `sqlite3_close_v2` 会把这样的连接留作 zombie，连同写事务的 WAL 写锁一直保留到那个游标被垃圾回收；被取消任务的栈帧只要还被取消异常引用，游标就不会被回收，其它写入方都得等满 busy_timeout。先回滚就释放写锁（测试 `tests/utils/db/sqlite/test_rollback_before_close.py`，空闲队列的认领路径见 `tests/agent/background_worker/test_idle_registry.py`）。
- **撕裂写守卫**：`cell_size_check=ON` 早检测 B-tree 撕裂；`page_count` 不变量检测物理截断。
- **隐私**：`SENSITIVE` 档 `secure_delete=ON`，删除即抹零（用于 PII 假名库）。
