# api/providers/

## 架构概述

LLM 供应商状态、额度实时监控与健康度探针 HTTP 端点层。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 模块导出与路由挂载声明 | ✅ |
| `balance_router.py` | 路由 | `GET /api/v1/providers/balance-gauges` 暴露当前激活 LLM Provider 额度与余额健康状态 | ✅ |
