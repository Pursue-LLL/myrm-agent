# api/internal/

## 架构概述

Control Plane → sandbox internal 控制端点（中断、killswitch、归档导入）。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `agent_interrupt.py` | 模块 | CP-to-sandbox internal endpoint for interrupting agent execution | ✅ |
| `import_archive.py` | 模块 | CP-to-sandbox internal endpoint for importing offboarding volume archive | ✅ |
| `skills_killswitch.py` | 模块 | CP-to-sandbox internal endpoint for remote skill killswitch management | ✅ |
| `import_agent_profile.py` | 模块 | CP-to-sandbox internal endpoint for marketplace Agent profile installation and force-push updates (with pre-snapshot for rollback; force-push never overwrites skill/subagent bindings established by import; None-valued package fields are skipped so NOT NULL columns never receive None) | ✅ |
| `org_policy_sync/`（子包） | 模块 | Org 策略同步域：`org_mcp_sync.py`（MCP 配置同步，normalizes missing `type`）、`org_model_policy_sync.py`（模型策略同步，POST 落盘 + revision + cache close；GET allowed-models 供 FE 灰显）、`org_managed_approval_policy_sync.py`（审批策略同步，POST + SSE fanout）。`org_policy_sync/__init__.py` 为聚合门面 | ✅ |
| `background_shell_status.py` | 模块 | CP-to-sandbox probe: running shell job count + `registry_ephemeral` (mirrors REST `shell_registry_is_ephemeral`) | ✅ |
| `agent_audit.py` | 模块 | CP-to-sandbox agent audit pull：GET `/api/admin/agent-audit/events` 按时间窗口拉取 harness JSONL event-log（agent 事件 SSOT）；`X-Telemetry-Token` 校验（`secrets.compare_digest` 恒定时间）+ hours/limit 钳制；截断前统计 `tool_call_total`（`tool_start`）、`security_event_total`（`security_audit`）与 `security_deny_total`（security_audit 事件内按 harness 权威 deny 语义 `BLOCK|DENY|REDACT|LEAK` 逐条计数，`core/security/audit.py` `record_decision` 口径）全量分类计数供 CP 聚合 | ✅ |
