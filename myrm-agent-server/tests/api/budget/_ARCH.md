# tests/api/budget/

## 架构概述

预算治理与渐进式花销干预 API 测试集。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 模块初始化 | — |
| `test_spend_control_api.py` | 测试 | 四级渐进式花销干预、软配额确认放行、Tier 4 批准与车队归因 API 单测 | ✅ |
| `test_channel_audit_api.py` | 测试 | 渠道审计接口的窗口契约（经 HTTP 与真实 SQLite）：`days` 取 1 与 90 通过，0、负数、91、10 的 6 次方一律在入口得到 422；不带 `days` 时 `period_days` 为 7 | ✅ |
