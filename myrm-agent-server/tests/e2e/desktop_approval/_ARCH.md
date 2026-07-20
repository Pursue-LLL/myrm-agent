# desktop_approval/

## Overview

Chrome MCP E2E helpers for Desktop Control approval (allow once / allow always → Settings revoke). Entry tests live in `../test_desktop_control_approval_chrome_e2e.py`.

## File Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `__init__.py` | Package | Docstring-only package marker (`tests/conftest.py` owns dev lib path) | ✅ |
| `conftest.py` | Guard | Session fcntl lock — one desktop approval E2E pytest at a time | ✅ |
| `constants.py` | Core | Timeouts, prompts, infra abort markers, `progress()` | ✅ |
| `infra_retry.py` | Core | `open_mcp_chat_page` (about:blank→navigate → recover → direct :3000); `is_retriable_page_transport` (detached Frame + mux timeout) | ✅ |
| `textedit_fixture.py` | Fixture | macOS TextEdit scroll target (background, minimized) | ✅ |
| `trust_api.py` | Core | HTTP helpers + safe revoke `data-testid` selector JS | ✅ |
| `gate_probe.py` | Core | Desktop tool activity, 60s idle fail-fast, provider diagnostics | ✅ |
| `turn_flow.py` | Core | `ensureComputerUseReady`/`openPanel` before approval click; scope-aware banner probe; DONE wait; Settings revoke | ✅ |
| `runner.py` | Core | `run_desktop_approval_chrome_e2e` + detached Frame → mux recover + reopen page | ✅ |

Unit smoke (no Chrome): `tests/unit/desktop_approval/test_trust_api_smoke.py`, `test_gate_probe_smoke.py`.

## Dependencies

- `myrm-agent/scripts/dev/lib/` — `cdp_chat_support`, `chrome_mcp_client`, `mcp_chat_ui`
- `tests/support/e2e_runtime_guard.py` — lease heartbeat, resource ledger
- Server trust API — `GET/DELETE /webui/desktop/trust/apps`, `POST /webui/desktop/approval/reset-runtime`

## Verification

```bash
MYRM_DESKTOP_APPROVAL_TIMEOUT_SEC=120 PYTEST_SAFE_TIMEOUT_SECONDS=7200 \
  CDMCP_MUX_REQUEST_TIMEOUT_MS=180000 MYRM_MUX_ALLOW_TIMEOUT_RESTART=1 \
  ./myrm ready --chrome && \
  ./myrm test myrm-agent/myrm-agent-server/tests/e2e/test_desktop_control_approval_chrome_e2e.py \
  -m chrome_e2e_desktop -n0
```

Backend must be running with `MYRM_DESKTOP_APPROVAL_TIMEOUT_SEC=120` (injected by `test.sh` for `-m chrome_e2e_desktop`; restart backend if env changed).
