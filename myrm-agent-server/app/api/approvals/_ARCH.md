# api/approvals/

## 架构概述

统一审批决策 HTTP 层：列出待审批、单条/批量 resolve，并通过事件总线恢复 Agent 流。

上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `router.py` | 路由 | `GET/POST /approvals` 审批 CRUD 与 resume 信号 | ✅ |
