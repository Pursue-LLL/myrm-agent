# desktop_control/

## Overview

Server-side desktop control gate: wires `ForegroundPermissionCallback` into harness `DesktopSession`,
handles per-app first approval (persisted under chat workspace volume), and emits SSE approval cards.

## File Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `gate.py` | Core | `DesktopControlGate` callback + registry + trust helpers. Timeout via `MYRM_DESKTOP_APPROVAL_TIMEOUT_SEC` (default 30s). Persists always-approved apps to `{workspace}/.agent/desktop_control/approved_apps.json` | ✅ |

## Trust API

| Route | Role |
|-------|------|
| `GET /webui/desktop/trust/apps` | List always-trusted apps from live gates + harness workspace disks + fallback workspace root |
| `DELETE /webui/desktop/trust/apps` | Revoke one trust key across live gates and persisted workspace stores |
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
| Test | `myrm-agent-server/tests/e2e/test_desktop_control_approval_chrome_e2e.py` (`@pytest.mark.chrome_e2e(lane="LIVE_AGENT", private_backend=False)`) |
| Preflight | `./myrm ready --chrome`；共享 `:8080` + 私有 chat workspace gate 文件；LIVE_AGENT cap 背压并行 |
| Gate trigger | Assert `GET /webui/desktop/approval/pending` → `server_pending>0`（禁止用 tool 名 substring 误判） |
| UI | `DesktopControlApprovalBanner` — `desktop-control-allow-once` / `allow-session` / `allow-always` / `deny` |
| Settings | `DesktopPermissionsCard` — `data-testid="desktop-trust-revoke-{trust_key}"` |
| E2E | `test_desktop_control_approval_chrome_e2e.py` + `tests/e2e/desktop_approval/` — allow_once + allow_session + allow_always→Settings revoke |
| Bridge | `E2EChatBridge.hasDone` 或 API `chat_messages_have_done()`；无 DONE 时 poll≥15 一次性 nudge |
| Signoff | `./myrm signoff chrome` → darwin `chrome_e2e_desktop` phase（3 cases；**E2E 未全绿前勿标 roadmap ✅**） |
| E2E env | `MYRM_DESKTOP_APPROVAL_TIMEOUT_SEC=120`（`test.sh` 对 `chrome_e2e_desktop` 自动 export） |
| Reset | `POST /webui/desktop/approval/reset-runtime` clears in-memory gate + reloads disk approvals |
| Retry | Product-only retries: `once` ≤3 / `always` ≤2; infra markers (Chrome/mux/wave) fail-fast — see Roadmap §12.1 |
