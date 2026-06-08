# api/audit/

## 架构概述

本目录模块说明。上级文档：[../../_ARCH.md](../../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Audit API module | ✅ |
| `alert_notifier.py` | 模块 | alert_notifier 模块实现 | — |
| `anomaly_detector.py` | 模块 | Bash命令异常检测 | ✅ |
| `auth_router.py` | 模块 | Auth audit query API. JSONL parsing is per-line fault-tolerant. """ | ✅ |
| `bash_router.py` | 模块 | Bash审计日志REST API | ✅ |
