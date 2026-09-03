"""Chrome READ E2E: tool_history_recovery progress step render."""

from __future__ import annotations

import json
import os
import sys
import time

import pytest

_LIB = os.path.join(os.path.dirname(__file__), "..", "..", "..", "scripts", "dev", "lib")
if _LIB not in sys.path:
    sys.path.insert(0, os.path.normpath(_LIB))

from tests.support.chrome_mcp_e2e import (
    _require_e2e_cdp_ready,  # noqa: E402
    dismiss_blocking_modals,
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_mcp_page,
    prepare_e2e_ui_session,
    wait_for_react_e2e_bridge,
    wait_for_state,
    warm_ui_route,
)

_MAX_ATTEMPTS = 3
_TRANSPORT_RETRY_MARKERS: tuple[str, ...] = (
    "open_mcp_page",
    "MUX",
    "Chrome MCP",
    "connection reset",
    "E2E_MUX_DAEMONS",
    "muxDaemons",
    "transport dead",
    "transport unavailable",
    "recover_mux_transport",
)

_FIXTURE_ANSWER = "Tool history recovery Chrome E2E fixture answer."


def _force_mux_heal_before_retry() -> None:
    _require_e2e_cdp_ready(budget_sec=45.0)
    from mux.attach_force_restart import force_mux_attach_restart_scoped

    force_mux_attach_restart_scoped(reason="tool_history recovery outer retry")
    time.sleep(3.0)


def _is_transport_retryable(exc: BaseException) -> bool:
    text = str(exc)
    return any(marker in text for marker in _TRANSPORT_RETRY_MARKERS)


def _messages_from_payload(payload: object) -> list[dict[str, object]]:
    if isinstance(payload, list):
        return [msg for msg in payload if isinstance(msg, dict)]
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, dict) and isinstance(data.get("messages"), list):
            return [msg for msg in data["messages"] if isinstance(msg, dict)]
        messages = payload.get("messages")
        if isinstance(messages, list):
            return [msg for msg in messages if isinstance(msg, dict)]
    return []


def _seed_fixture(api_url: str) -> dict[str, str]:
    seeded = http_json(
        "POST",
        f"{api_url}/api/v1/chats/test/seed-tool-history-recovery-fixture",
    )
    assert isinstance(seeded, dict)
    chat_id = str(seeded.get("chat_id") or "")
    assert chat_id.startswith("e2etoolhist")
    return {"chat_id": chat_id}


def _ensure_fixture_assistant_ready(api_url: str, chat_id: str, *, timeout_sec: float = 45.0) -> None:
    deadline = time.monotonic() + timeout_sec
    last_error = "timeout"
    while time.monotonic() < deadline:
        try:
            payload = http_json("GET", f"{api_url}/api/v1/chats/{chat_id}/messages")
            messages = _messages_from_payload(payload)
            assistant = next(
                (msg for msg in messages if msg.get("role") == "assistant"),
                None,
            )
            if isinstance(assistant, dict):
                content = str(assistant.get("content") or "")
                if _FIXTURE_ANSWER not in content:
                    last_error = f"assistant content missing target; len={len(content)}"
                else:
                    metadata = assistant.get("metadata")
                    meta = metadata if isinstance(metadata, dict) else {}
                    steps = meta.get("progressSteps")
                    if isinstance(steps, list) and any(
                        isinstance(step, dict) and str(step.get("step_key") or "") == "tool_history_recovery" for step in steps
                    ):
                        return
                    last_error = f"metadata missing tool_history_recovery step: {meta!r}"
            else:
                last_error = f"assistant missing; count={len(messages)}"
        except (RuntimeError, TimeoutError, OSError, ValueError) as exc:
            last_error = str(exc)
        time.sleep(0.3)
    raise AssertionError(f"tool_history fixture not ready chat={chat_id}: {last_error}")


_RECOVERY_STEP_JS = """(() => {
  const store = window.__myrmChatStore?.getState?.();
  const msgs = store?.messages || [];
  for (const msg of msgs) {
    const metaSteps = Array.isArray(msg.metadata?.progressSteps)
      ? msg.metadata.progressSteps
      : [];
    const steps = (msg.progressSteps?.length ? msg.progressSteps : metaSteps) || [];
    for (const step of steps) {
      const key = String(step.step_key || step.tool_name || '');
      if (key === 'tool_history_recovery') {
        return { ready: true, step_key: key, status: step.status || null };
      }
    }
  }
  return { ready: false, msg_count: msgs.length };
})()"""


_PROGRESS_DOM_READY_JS = """(() => {
  window.scrollTo(0, document.body.scrollHeight);
  const toggle = document.querySelector('[data-testid="progress-steps-toggle"]');
  const panel = document.querySelector('[data-testid="progress-steps-panel"]');
  return {
    ready: !!(toggle || panel),
    hasToggle: !!toggle,
    hasPanel: !!panel,
  };
})()"""


_RECOVERY_LABEL_JS = """(() => {
  window.scrollTo(0, document.body.scrollHeight);
  const toggle = document.querySelector('[data-testid="progress-steps-toggle"]');
  if (toggle && toggle.getAttribute('data-expanded') !== 'true') {
    toggle.click();
  }
  const panel = document.querySelector('[data-testid="progress-steps-panel"]');
  const text = panel?.textContent || document.body?.textContent || '';
  const hasRecovery =
    text.includes('Conversation history repaired') ||
    text.includes('对话历史已自动修复');
  return {
    ready: hasRecovery,
    hasPanel: !!panel,
    hasToggle: !!toggle,
    text_head: text.slice(0, 600),
  };
})()"""


_DISMISS_MIGRATION_JS = """(() => {
  try {
    sessionStorage.setItem('migration_discovery_dismissed', 'true');
    sessionStorage.setItem('competitor_migration_dismissed', 'true');
  } catch (err) {
    return { ok: false, err: String(err) };
  }
  return { ok: true };
})()"""


def _attach_chat_probe(chat_id: str) -> str:
    chat_id_json = json.dumps(chat_id)
    return f"""(async () => {{
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge?.attachToChat) {{
    return {{ ok: false, err: 'no-bridge' }};
  }}
  await bridge.attachToChat({chat_id_json});
  const snap = bridge.turnSnapshot?.() ?? {{}};
  return {{
    ok: snap.chatId === {chat_id_json} && (snap.userCount ?? 0) >= 1,
    snap,
  }};
}})()"""


def _ensure_shpoib_api_binding(
    client: object,
    page: object,
    api_base: str,
    *,
    timeout_sec: float = 90.0,
) -> None:
    """Inject and wait for SHPOIB API binding on shared :3000 UI."""
    from cdp_chat.support import (
        E2E_API_BINDING_PROBE_JS,
        e2e_api_base_inject_js,
        e2e_runtime_binding_source,
        wait_e2e_provider_ready,
    )

    expected = api_base.rstrip("/")
    deadline = time.monotonic() + timeout_sec
    last_probe: dict[str, object] = {}
    while time.monotonic() < deadline:
        raw = client.evaluate(  # type: ignore[attr-defined]
            page,
            E2E_API_BINDING_PROBE_JS,
            timeout_sec=15.0,
        )
        last_probe = raw if isinstance(raw, dict) else {"value": raw}
        actual = str(last_probe.get("apiBase") or "").rstrip("/")
        if actual == expected:
            return
        try:
            provider_ready = wait_e2e_provider_ready(api_url=expected, timeout_sec=5.0)
        except (OSError, TimeoutError, RuntimeError, ValueError):
            provider_ready = False
        if provider_ready or not actual:
            source = e2e_runtime_binding_source()
            if source:
                client.evaluate(  # type: ignore[attr-defined]
                    page,
                    f"(() => {{{source} return true; }})()",
                    timeout_sec=15.0,
                )
            else:
                client.evaluate(  # type: ignore[attr-defined]
                    page,
                    e2e_api_base_inject_js(expected),
                    timeout_sec=15.0,
                )
        time.sleep(0.5)
    raise AssertionError(f"SHPOIB API binding failed: expected {expected!r}, probe={last_probe!r}")


def _run_read_ui_assertions(api_url: str, ui_url: str, chat_id: str) -> None:
    _ensure_fixture_assistant_ready(api_url, chat_id)
    warm_ui_route(f"/{chat_id}")
    page_url = f"{ui_url.rstrip('/')}/{chat_id}"

    with open_mcp_page(page_url, timeout_ms=120_000) as (client, page):
        client.evaluate(page, _DISMISS_MIGRATION_JS, timeout_sec=15.0)

        bridge_ready = wait_for_react_e2e_bridge(
            client,
            page,
            timeout_sec=90.0,
            page_url=page_url,
        )
        assert bridge_ready.get("ready") is True, json.dumps(bridge_ready, ensure_ascii=False)
        _ensure_shpoib_api_binding(client, page, api_url.rstrip("/"))

        attached = client.evaluate(
            page,
            _attach_chat_probe(chat_id),
            timeout_sec=90.0,
        )
        assert isinstance(attached, dict) and attached.get("ok") is True, attached

        dismiss_blocking_modals(client, page)

        step_state = wait_for_state(
            client,
            page,
            _RECOVERY_STEP_JS,
            timeout_sec=60.0,
        )
        assert step_state.get("ready") is True, json.dumps(step_state, ensure_ascii=False)

        dom_ready = wait_for_state(
            client,
            page,
            _PROGRESS_DOM_READY_JS,
            timeout_sec=60.0,
        )
        assert dom_ready.get("ready") is True, json.dumps(dom_ready, ensure_ascii=False)

        label_state = wait_for_state(
            client,
            page,
            _RECOVERY_LABEL_JS,
            timeout_sec=60.0,
        )
        assert label_state.get("ready") is True, json.dumps(label_state, ensure_ascii=False)


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_tool_history_recovery_progress_step_render() -> None:
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(api_url)
    seeded = _seed_fixture(api_url)
    chat_id = seeded["chat_id"]

    last_error: BaseException | None = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            _run_read_ui_assertions(api_url, ui_url, chat_id)
            return
        except Exception as exc:
            last_error = exc
            if attempt >= _MAX_ATTEMPTS or not _is_transport_retryable(exc):
                raise
            _force_mux_heal_before_retry()

    if last_error is not None:
        raise last_error
