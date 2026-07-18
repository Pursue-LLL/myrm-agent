# desktop_control/

## Overview

Server-side desktop control gate: wires `ForegroundPermissionCallback` into harness `DesktopSession`,
handles per-app first approval (persisted under chat workspace volume), and emits SSE approval cards.

## File Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `gate.py` | Core | `DesktopControlGate` callback + `DesktopApprovalRegistry` + resolve helper. Empty `app_name` is fail-closed (never preapproved). Persists always-approved apps to `{workspace}/.agent/desktop_control/approved_apps.json` | ✅ |

## Dependencies

- `myrm_agent_harness.toolkits.computer_use` (ForegroundPermissionCallback, ExecutionMode)
- `myrm_agent_harness.utils.runtime.progress_sink` (SSE emit during tool execution)
- `app.ai_agents.general_agent.tool_setup` (session wiring)
- `app.api.webui.router` (`POST /webui/desktop/approval/resolve`)

## Verification (Chrome MCP E2E)

| Item | Detail |
|------|--------|
| Test | `myrm-agent-server/tests/e2e/test_desktop_control_approval_chrome_e2e.py` (`@pytest.mark.chrome_e2e(lane="LIVE_AGENT")`) |
| Preflight | `./myrm ready --chrome`；`MYRM_LIVE_AGENT_MAX_CONCURRENT=1` 推荐 isolated 跑 |
| Gate trigger | Assert `GET /webui/desktop/approval/pending` → `server_pending>0`（禁止用 tool 名 substring 误判） |
| UI | `DesktopControlApprovalBanner` — `data-testid="desktop-control-allow-once"` / `desktop-control-deny` |
| Bridge | `E2EChatBridge.turnSnapshot().hasDone` 全量 DONE 匹配 + post-approval stream/API fallback |
| Signoff | v54 `./myrm signoff chrome --stress xdist4 --fault sigterm-goal-cache` → `ok: true`（matrix 14-case `--ignore` desktop；desktop 单独 E2E 绿 `/tmp/myrm-desktop-goal-final18.log` 885s） |
| Reset | `POST /webui/desktop/approval/reset-runtime` clears in-memory gate + reloads disk approvals |
