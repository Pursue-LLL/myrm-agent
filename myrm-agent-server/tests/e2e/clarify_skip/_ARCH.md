# clarify_skip/

## Overview

Chrome MCP E2E helpers for the clarify Skip live flow: a structured clarification card opens, Skip resumes the paused agent. The entry test lives in `../test_clarify_skip_chrome_e2e.py`; this package holds the steps it composes.

## File Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `__init__.py` | Package | Docstring-only package marker | ✅ |
| `constants.py` | Core | Page origin, prompts and the API wait budget (`CLARIFY_SKIP_API_WAIT_SEC` overrides the contract value) | ✅ |
| `bridge_js.py` | Core | Page-side scripts evaluated through the E2E chat bridge: enable structured clarify, pin the lite model, dismiss the migration prompt, release the UI stream, read clarify-form readiness, click Skip, read the UI skip-done state | ✅ |
| `chat_actions.py` | Core | Chat-page setup and stream hand-over: prepare a fresh chat, release the UI SSE lease so the API can resume the paused run | ✅ |
| `waits.py` | Core | Polling layer: the clarification card (API pending first, DOM second; under `E2E_SIGNOFF` the API stream starts it when the page does not show it), skip evidence from messages or the UI bridge, the Skip button; every loop touches wall-clock progress and the heartbeat | ✅ |
| `resume.py` | Core | API skip resume addressed to the card's pause, with retries; classifies no-user-query errors, progress stalls and transient transport errors | ✅ |
| `skip_flow.py` | Core | Escalation ladder: UI bridge skip, then DOM skip, then API resume; the first path that proves the skip reached the agent wins | ✅ |
| `flow.py` | Core | One live turn end to end: open the page, send the prompt, reach the card, skip it, check the chat | ✅ |

## Dependencies

- Inside the package: `constants` and `bridge_js` have no package dependency; `chat_actions` ← `constants` · `bridge_js`; `waits` ← `chat_actions` · `constants` · `bridge_js`; `resume` ← `chat_actions` · `constants`; `skip_flow` ← `waits` · `resume` · `chat_actions` · `constants` · `bridge_js`; `flow` ← `skip_flow` · `waits` · `chat_actions` · `constants` · `bridge_js`
- `myrm-agent/scripts/dev/lib/` — `cdp_chat/support/`, `cdp_chat/mcp_ui.py`, `cdp_chat/ui.py`, `chrome_mcp/client.py`, `dev_gate/contract`, `e2e_core/orchestrator`, `e2e_session_runtime/heartbeat.py`
- `tests/support/e2e_runtime_guard.py` — resource ledger
- `tests/api/agent/utils.py` — lite model selection
