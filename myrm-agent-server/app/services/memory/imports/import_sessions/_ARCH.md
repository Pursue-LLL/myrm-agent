# memory/imports/import_sessions/

## 架构概述

记忆导入审查会话：查询、dry-run/confirm、回滚与就绪诊断分层，`__init__.py` 是唯一门面。上级：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 门面 | 导出服务、异常、就绪事实与 dry-run 常量 | ✅ |
| `base.py` | 基础 | 异常、`ImportReadinessRecheckFacts`、常量、纯函数与共享状态 | ✅ |
| `queries.py` | 核心 | 批次/会话查询、过期清理与指标 | ✅ |
| `dry_run.py` | 核心 | 创建 dry-run 会话与确认导入 | ✅ |
| `rollback.py` | 核心 | 回滚预览、执行与不完整回滚恢复 | ✅ |
| `readiness.py` | 核心 | 诊断、就绪复核与首轮结果保存 | ✅ |
| `service.py` | 核心 | 组合四个阶段并建立 db/ledger 状态 | ✅ |

## 依赖关系

- `dry_run.py` → `base.py`
- `queries.py` → `base.py`
- `readiness.py` → `base.py`
- `rollback.py` → `base.py`
- `service.py` → `base.py`
- `service.py` → `dry_run.py`
- `service.py` → `queries.py`
- `service.py` → `readiness.py`
- `service.py` → `rollback.py`
