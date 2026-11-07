# memory/imports/import_sessions/

## 架构概述

记忆导入审查会话：查询、dry-run/confirm、回滚与就绪诊断分层，`__init__.py` 是唯一门面。上级：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 职责 |
|------|------|
| `__init__.py` | 导出服务、异常、就绪事实与 dry-run 常量 |
| `base.py` | 异常、`ImportReadinessRecheckFacts`、常量、纯函数与共享状态 |
| `queries.py` | 批次/会话查询、过期清理与指标 |
| `dry_run.py` | 创建 dry-run 会话与确认导入 |
| `rollback.py` | 回滚预览、执行与不完整回滚恢复 |
| `readiness.py` | 诊断、就绪复核与首轮结果保存 |
| `service.py` | 组合四个阶段并建立 db/ledger 状态 |
