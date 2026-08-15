# api/internal/org_policy_sync/

## 架构概述

Control Plane → sandbox 的 Org 策略同步域：把 CP 下发的 MCP 配置、模型策略与审批策略同步到当前沙箱实例。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 门面 | 聚合子模块导出，保持 `app.api.internal` 包外 import 稳定 | ✅ |
| `org_mcp_sync.py` | 模块 | Org MCP 配置同步端点：normalize 缺失的 `type` 字段，合并替换沙箱 MCP 配置 | ✅ |
| `org_model_policy_sync.py` | 模块 | 模型策略同步：POST 落盘 + revision 递增 + cache close；GET allowed-models 供前端灰显 | ✅ |
| `org_managed_approval_policy_sync.py` | 模块 | 托管审批策略同步：POST 落盘 + SSE fanout 通知前端刷新 | ✅ |
