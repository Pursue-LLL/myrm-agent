# api/internal/

## 架构概述

Control Plane → sandbox internal 控制端点（中断、killswitch、Agent 档案导入、策略同步、审计拉取）。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `agent_interrupt.py` | 模块 | CP-to-sandbox internal endpoint for interrupting agent execution | ✅ |
| `skills_killswitch.py` | 模块 | CP-to-sandbox internal endpoint for remote skill killswitch management | ✅ |
| `org_policy_sync/`（子包） | 模块 | Org 策略同步域：`org_mcp_sync.py`（MCP 配置同步，normalizes missing `type`）、`org_model_policy_sync.py`（模型策略同步，POST 落盘 + revision + cache close；GET allowed-models 供 FE 灰显）、`org_managed_approval_policy_sync.py`（审批策略同步，POST + SSE fanout）。`org_policy_sync/__init__.py` 为聚合门面 | ✅ |
| `background_shell_status.py` | 模块 | CP-to-sandbox probe: running shell job count + `registry_ephemeral` (mirrors REST `shell_registry_is_ephemeral`) | ✅ |
| `agent_audit.py` | 模块 | CP-to-sandbox agent audit pull：GET `/api/admin/agent-audit/events` 按时间窗口拉取 harness JSONL event-log（agent 事件 SSOT）；`X-Telemetry-Token` 校验（`secrets.compare_digest` 恒定时间）+ hours/limit 钳制；截断前统计 `tool_call_total`（`tool_start`）、`security_event_total`（`security_audit`）与 `security_deny_total`（security_audit 事件内按 harness `is_policy_denial()`（决策名含 `BLOCK|DENY|REDACT|LEAK`，即 `policy_denial_total` 的口径）逐条计数）全量分类计数供 CP 聚合；返回前对当前页的事件载荷再做一次与写入侧相同的脱敏（harness `sanitize_event_data`，在工作线程里执行，约 0.4 毫秒每条），早于某条规则写入的、或绕过日志器直接写后端的明文不出沙箱，计数仍按未脱敏的全量事件计算 | ✅ |
