# desktop_approval/

## Overview

Chrome MCP E2E helpers for Desktop Control approval (allow once / allow always → Settings revoke). Entry tests live in `../test_desktop_control_approval_chrome_e2e.py`.

## File Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `__init__.py` | Bootstrap | Inserts `myrm-agent/scripts/dev/lib` on `sys.path` for MCP helpers | ✅ |
| `constants.py` | Core | Timeouts, prompts, infra abort markers, `progress()` | ✅ |
| `infra_retry.py` | Core | `open_mcp_chat_page` (about:blank + navigate), mux retry classifiers | ✅ |
| `textedit_fixture.py` | Fixture | macOS TextEdit scroll target (background, minimized) | ✅ |
| `trust_api.py` | Core | HTTP helpers: pending count, trust list, clear approvals | ✅ |
| `gate_probe.py` | Core | Desktop tool activity + interact gate nudge logic | ✅ |
| `turn_flow.py` | Core | Approval attempt, DONE wait, Settings revoke verification | ✅ |
| `runner.py` | Core | `run_desktop_approval_chrome_e2e` orchestration + Chrome MCP lifecycle | ✅ |

## Dependencies

- `myrm-agent/scripts/dev/lib/` — `cdp_chat_support`, `chrome_mcp_client`, `mcp_chat_ui`
- `tests/support/e2e_runtime_guard.py` — lease heartbeat, resource ledger
- Server trust API — `GET/DELETE /webui/desktop/trust/apps`, `POST /webui/desktop/approval/reset-runtime`

## Verification

```bash
PYTEST_SAFE_TIMEOUT_SECONDS=7200 ./myrm test \
  myrm-agent/myrm-agent-server/tests/e2e/test_desktop_control_approval_chrome_e2e.py \
  -m chrome_e2e_desktop -n0
```
