# desktop_approval/

## Overview

Chrome MCP E2E helpers for Desktop Control approval (allow once / allow always → Settings revoke). Entry tests live in `../test_desktop_control_approval_chrome_e2e.py`.

## File Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `__init__.py` | Package | Docstring-only package marker (`tests/conftest.py` owns dev lib path) | ✅ |
| `conftest.py` | Guard | Session fcntl lock — one desktop approval E2E pytest at a time | ✅ |
| `constants.py` | Core | Timeouts (incl. `APPROVAL_CLICK_DEADLINE_SEC` SSOT with gate env), prompts, infra abort markers, `progress()` | ✅ |
| `infra_retry.py` | Core | `heal_chrome_attach_before_reopen`（R46 attach SSOT）+ `open_mcp_chat_page`（about:blank→navigate → recover → direct :3000）；`is_retriable_page_transport` | ✅ |
| `textedit_fixture.py` | Fixture | macOS TextEdit scroll target (foreground for AX @drefs during agent tools)；AX 空树触发 degraded cooldown，且按当前 pytest scope 隔离，避免跨用例污染与重复高耗时重建；strict 模式下（`MYRM_DESKTOP_E2E_STRICT_FALLBACK_MODE=1`）AX 不可用直接 fail-fast | ✅ |
| `trust_api.py` | Core | HTTP helpers（统一走 `cdp_chat_support._e2e_api_urlopen` loopback 校验 + 重试）+ `fetch_pending_approval_request_ids` + safe revoke `data-testid` selector JS | ✅ |
| `gate_probe.py` | Core | Desktop tool activity, idle fail-fast, TextEdit foreground during api_only wait, nudge routing；API poll `to_thread + wait_for` wall-timeout guard，防止 shared_hot 长阻塞；fallback budget（synthetic dref / pending seed）超限 fail-fast，支持 strict 模式（`MYRM_DESKTOP_E2E_STRICT_FALLBACK_MODE=1`）验真并在 signoff 默认开启；返回 `pendingSource` 区分真实/合成 pending | ✅ |
| `turn_flow.py` | Core | navigate guard + E2E bridge openPanel/sync; scope-aware banner probe; DONE wait; Settings revoke | ✅ |
| `runner.py` | Core | `run_desktop_approval_chrome_e2e` + retry 路径 attach heal → mux recover → reopen page | ✅ |

Unit smoke (no Chrome): `tests/unit/desktop_approval/test_trust_api_smoke.py`, `test_gate_probe_smoke.py`.

## Dependencies

- `myrm-agent/scripts/dev/lib/` — `cdp_chat_support`, `chrome_mcp_client`, `mcp_chat_ui`
- `tests/support/e2e_runtime_guard.py` — lease heartbeat, resource ledger
- Server trust API — `GET/DELETE /webui/desktop/trust/apps`, `POST /webui/desktop/approval/reset-runtime`

## Verification

```bash
MYRM_DESKTOP_APPROVAL_TIMEOUT_SEC=120 PYTEST_SAFE_TIMEOUT_SECONDS=720 \
  CDMCP_MUX_REQUEST_TIMEOUT_MS=180000 MYRM_MUX_ALLOW_TIMEOUT_RESTART=1 \
  ./myrm ready --chrome && \
  ./myrm test myrm-agent/myrm-agent-server/tests/e2e/test_desktop_control_approval_chrome_e2e.py \
  -m chrome_e2e_desktop -n0
```

Backend must be running with `MYRM_DESKTOP_APPROVAL_TIMEOUT_SEC=120` (injected by `test.sh` for `-m chrome_e2e_desktop`; restart backend if env changed).
