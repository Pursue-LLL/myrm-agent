# database/migrations/

## 架构概述

数据库迁移账本与执行器：`schema/`、`indexes/` 各自按版本区间连续切片并在子包入口顺序拼接，保证 `enumerate` 出来的版本号与拆分前完全一致；`runner.py` 只负责执行。上级：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 门面 | 导出账本、执行器与一次性 SQL | ✅ |
| `schema/` | 子包 | schema 迁移语句，按版本区间拆成两个连续文件 | ✅ |
| `indexes/` | 子包 | 索引迁移语句，按版本区间拆成两个连续文件 | ✅ |
| `runner.py` | 执行 | `run_migrations` / `create_indexes` / `ensure_raw_sql_schema` | ✅ |
| `legacy_sql.py` | 数据 | 遗留 workspace 路径清理、wakeup 回填、审批拒绝 SQL | ✅ |
