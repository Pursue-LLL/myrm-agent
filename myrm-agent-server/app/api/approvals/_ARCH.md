# api/approvals/

## 架构概述

本目录模块说明。上级文档：[../../_ARCH.md](../../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Approval HTTP endpoints. | ✅ |
| `router.py` | 路由 | 提供统一的审批决策接口。处理挂起任务的 approve/deny，恢复底层 agent 执行。 """ | ✅ |
