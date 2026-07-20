# desktop_control/

## Overview

Server-side desktop control gate: wires `ForegroundPermissionCallback` into harness `DesktopSession`,
handles per-app first approval (persisted under chat workspace volume), and emits SSE approval cards.

## File Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `gate.py` | Core | `DesktopControlGate` callback + `DesktopApprovalRegistry` + trust list/revoke helpers. Empty `app_name` is fail-closed (never preapproved). Persists always-approved apps to `{workspace}/.agent/desktop_control/approved_apps.json` keyed by stable `app_id` via harness `resolve_trust_key` | ✅ |

## Trust API

| Route | Role |
|-------|------|
| `GET /webui/desktop/trust/apps` | List always-trusted apps (`trust_key`, `display_name`, `app_id`, `scope`) |
| `DELETE /webui/desktop/trust/apps` | Revoke one trust key (JSON body `{trust_key}`); updates disk + live gates for workspace only |
| `POST /webui/desktop/approval/reset-runtime` | Clears in-memory session approvals and reloads persisted always-trusted apps |

Revoke does **not** call `reset_all_runtime_approval_state()` — other apps' session approvals stay intact.

## Dependencies

- `myrm_agent_harness.toolkits.computer_use` (ForegroundPermissionCallback, ExecutionMode)
- `myrm_agent_harness.toolkits.computer_use.app_identity` (resolve_trust_key, trust_key_matches)
- `myrm_agent_harness.utils.runtime.progress_sink` (SSE emit during tool execution)
- `app.ai_agents.general_agent.tool_setup` (session wiring)
- `app.api.webui.router` (`POST /webui/desktop/approval/resolve`)

## Verification (Chrome MCP E2E)

| Item | Detail |
|------|--------|
| Test | `myrm-agent-server/tests/e2e/test_desktop_control_approval_chrome_e2e.py` (`@pytest.mark.chrome_e2e(lane="LIVE_AGENT")`) |
| Preflight | `./myrm ready --chrome`；默认 LIVE_AGENT cap=2（与其他 chrome_e2e 并行，背压等待） |
| Gate trigger | Assert `GET /webui/desktop/approval/pending` → `server_pending>0`（禁止用 tool 名 substring 误判） |
| UI | `DesktopControlApprovalBanner` — `data-testid="desktop-control-allow-once"` / `desktop-control-deny` |
| Bridge | `E2EChatBridge.hasDone` 或 API `chat_messages_have_done()`；无 DONE 时 poll≥15 一次性 nudge |
| Signoff | `./myrm signoff chrome --stress xdist4 --fault sigterm-goal-cache` → matrix `chrome_e2e and not chrome_e2e_desktop` + darwin `chrome_e2e_desktop` phase（preflight + E2E）；desktop 独立 E2E 绿 R4 `/tmp/myrm-desktop-verify-r4.log` 187s |
| Reset | `POST /webui/desktop/approval/reset-runtime` clears in-memory gate + reloads disk approvals |
