# database/operations 模块架构

数据库运维工具子包。备份、容灾恢复、SQLite 忙/锁处理、FastAPI 异常处理器、遗留数据清理。

## 文件清单

| 文件 | 职责 |
|------|------|
| `backup.py` | SQLite 备份管理器工厂。`get_sqlite_backup_manager()` 返回配置好的 `SQLiteBackupManager` 实例（含 `:memory:` 安全检查），所有备份/恢复调用方统一使用 |
| `recovery.py` | 数据库容灾层。提供 `rescue_database()` 与 `rescue_database_detailed()`，调用 Harness `SQLiteRowidSalvageEngine` 执行非破坏性 B-Tree 坏页二分跳跃打捞、孤儿会话 Stub 自愈、FTS 全文索引原生重建及二级索引与视图延迟批量恢复；常规热备份与快照恢复由 `SQLiteBackupManager` 负责 |
| `sqlite_storage_busy.py` | 识别 SQLite 忙/锁异常；`sqlite_busy_retry_after_seconds()` 基于 `get_sqlite_busy_timeout_ms()` |
| `db_operational_handlers.py` | `register_database_operational_handlers(app)`：`sqlite3` 与 SQLAlchemy `OperationalError` → SQLite 忙 **503/51005**、其余 **500/51002** |
| `legacy_canvas_cleanup.py` | 删除 legacy 本地目录 `~/.myrm/canvas/`（tldraw snapshot）；由 `init_database` 在迁移后调用 |
