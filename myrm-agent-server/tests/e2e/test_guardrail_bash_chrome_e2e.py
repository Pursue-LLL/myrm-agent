"""Chrome READ E2E: bash myrm_tools guardrail Badge (安全拦截 / Safety Blocked)."""

from __future__ import annotations

import json
import os
import sys
import time

import pytest

_LIB = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "scripts", "dev", "lib"
)
if _LIB not in sys.path:
    sys.path.insert(0, os.path.normpath(_LIB))

from tests.support.chrome_mcp_e2e import (  # noqa: E402
    _require_e2e_cdp_ready,
    dismiss_blocking_modals,
    ensure_desktop_viewport,
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_mcp_page,
    prepare_e2e_ui_session,
    wait_for_react_e2e_bridge,
    wait_for_state,
    warm_ui_route,
)

_VARIANTS: tuple[str, ...] = ("direct_import", "pipe_stdin", "python_m")
_FIXTURE_ANSWER = "Guardrail bash Chrome E2E fixture answer."
_MAX_ATTEMPTS = 3
_TRANSPORT_RETRY_MARKERS: tuple[str, ...] = (
    "open_mcp_page",
    "MUX",
    "CDP",
    "Runtime.evaluate",
    "Browser Orchestrator",
    "CDP request timeout",
    "Chrome MCP",
    "connection reset",
    "wait_for_state",
    "Browser state did not become ready",
    "Page shell did not hydrate",
    "E2E_MUX_DAEMONS",
    "muxDaemons",
    "transport dead",
    "transport unavailable",
    "recover_mux_transport",
    "recover_mux",
    "chrome-error",
    "PARENT_LEASE_NOT_ACTIVE",
    "E2E_LEASE_INVALID",
    "LEASE_NOT_ACTIVE",
    "no-panel",
    "no-bridge",
    "React E2E bridge",
    "apiBase': None",
    "apiBase\": None",
    "E2E_ORCHESTRATOR_LEASE_DENIED",
    "ORCHESTRATOR_LEASE_DENIED",
    "MUX_ATTACH_RESTART_BLOCKED_PARALLEL",
)


def _bridge_ready_timeout_sec() -> float:
    try:
        from e2e_shared_ui_hydrate import parallel_shared_ui_hydrate_queue_enabled

        if parallel_shared_ui_hydrate_queue_enabled():
            return 180.0
    except ImportError:
        pass
    return 90.0


def _attach_eval_timeout_sec() -> float:
    """Scale attachToChat evaluate under parallel mux (R138 parity)."""
    return _bridge_ready_timeout_sec()


def _force_mux_heal_before_retry() -> None:
    _require_e2e_cdp_ready(budget_sec=45.0)
    from mux_attach_force_restart import force_mux_attach_restart_scoped

    force_mux_attach_restart_scoped(reason="guardrail bash outer retry")
    time.sleep(3.0)


def _is_transport_retryable(exc: BaseException) -> bool:
    text = str(exc)
    if "E2E_USER_CLOSED_TAB" in text:
        return False
    return any(marker in text for marker in _TRANSPORT_RETRY_MARKERS)


def _messages_from_payload(payload: object) -> list[object]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, dict) and isinstance(data.get("messages"), list):
            return data["messages"]
        raw_messages = payload.get("messages")
        if isinstance(raw_messages, list):
            return raw_messages
    return []


def _seed_fixture(api_url: str, *, variant: str) -> dict[str, str]:
    seeded = http_json(
        "POST",
        f"{api_url}/api/v1/chats/test/seed-guardrail-bash-fixture?variant={variant}",
    )
    assert isinstance(seeded, dict)
    chat_id = str(seeded.get("chat_id") or "")
    assert chat_id.startswith("e2eguard")
    payload = http_json("GET", f"{api_url}/api/v1/chats/{chat_id}/messages")
    messages = _messages_from_payload(payload)
    assert len(messages) >= 2, payload
    return {"chat_id": chat_id, "variant": variant}


_GUARDRAIL_CATEGORY_JS = """(() => {
  const store = window.__myrmChatStore?.getState?.();
  const msgs = store?.messages || [];
  for (const msg of msgs) {
    const metaSteps = Array.isArray(msg.metadata?.progressSteps)
      ? msg.metadata.progressSteps
      : [];
    const steps = (msg.progressSteps?.length ? msg.progressSteps : metaSteps) || [];
    for (const step of steps) {
      if (String(step.error_category || '') === 'guardrail_blocked') {
        return {
          ready: true,
          step_key: step.step_key || step.tool_name || null,
          status: step.status || null,
        };
      }
    }
  }
  return { ready: false, msg_count: msgs.length };
})()"""


_GUARDRAIL_BADGE_JS = """(() => {
  window.scrollTo(0, document.body.scrollHeight);
  const toggle = document.querySelector('[data-testid="progress-steps-toggle"]');
  if (toggle && toggle.getAttribute('data-expanded') !== 'true') {
    toggle.click();
  }
  const panel = document.querySelector('[data-testid="progress-steps-panel"]');
  const text = panel?.textContent || document.body?.textContent || '';
  const hasBadge =
    text.includes('安全拦截') || text.includes('Safety Blocked');
  return {
    ready: hasBadge,
    hasBadge,
    hasPanel: !!panel,
    hasToggle: !!toggle,
    text_head: text.slice(0, 600),
  };
})()"""


_PROGRESS_DOM_READY_JS = """(() => {
  window.scrollTo(0, document.body.scrollHeight);
  const toggle = document.querySelector('[data-testid="progress-steps-toggle"]');
  const panel = document.querySelector('[data-testid="progress-steps-panel"]');
  const assistants = document.querySelectorAll('[data-test-id="assistant-message"]').length;
  return {
    ready: assistants >= 1 && !!(toggle || panel),
    hasToggle: !!toggle,
    hasPanel: !!panel,
    assistants,
  };
})()"""


_EXPAND_PROGRESS_JS = """(() => {
  const toggle = document.querySelector('[data-testid="progress-steps-toggle"]');
  if (toggle) {
    if (toggle.getAttribute('data-expanded') !== 'true') {
      toggle.click();
    }
    return { ok: true, via: 'toggle' };
  }
  const panel = document.querySelector('[data-testid="progress-steps-panel"]');
  if (panel) {
    panel.click();
    return { ok: true, via: 'panel' };
  }
  return { ok: false, err: 'no-toggle-or-panel' };
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


def _ensure_fixture_assistant_ready(
    api_url: str, chat_id: str, *, timeout_sec: float = 45.0
) -> None:
    """Poll private API before Chrome — SHPOIB backend may lag seed under parallel mux."""
    deadline = time.monotonic() + timeout_sec
    last_error = "timeout"
    while time.monotonic() < deadline:
        try:
            payload = http_json("GET", f"{api_url}/api/v1/chats/{chat_id}/messages")
            messages = _messages_from_payload(payload)
            assistant = next(
                (
                    msg
                    for msg in messages
                    if isinstance(msg, dict) and msg.get("role") == "assistant"
                ),
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
                    if isinstance(steps, list) and len(steps) >= 1:
                        return
                    last_error = f"metadata missing progressSteps: {meta!r}"
            else:
                last_error = f"assistant missing; count={len(messages)}"
        except (RuntimeError, TimeoutError, OSError, ValueError) as exc:
            last_error = str(exc)
        time.sleep(0.3)
    raise AssertionError(f"guardrail fixture not ready chat={chat_id}: {last_error}")


def _ensure_shpoib_api_binding(
    client: object,
    page: object,
    api_base: str,
    *,
    timeout_sec: float = 90.0,
) -> None:
    """Inject and wait for private SHPOIB API binding on shared :3000 UI."""
    from cdp_chat_support import (  # type: ignore[import-not-found]
        E2E_API_BINDING_PROBE_JS,
        e2e_api_base_inject_js,
        e2e_runtime_binding_source,
        e2e_runtime_bootstrap_apply_js,
        wait_e2e_provider_ready,
    )

    expected = api_base.rstrip("/")
    if not wait_e2e_provider_ready(api_url=expected, timeout_sec=min(30.0, timeout_sec)):
        raise AssertionError(f"private API not ready before SHPOIB bind: {expected!r}")

    bootstrap_js = e2e_runtime_bootstrap_apply_js(expected)
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
        remaining = max(0.0, deadline - time.monotonic())
        if bootstrap_js:
            client.evaluate(  # type: ignore[attr-defined]
                page,
                bootstrap_js,
                timeout_sec=min(45.0, max(5.0, remaining)),
            )
            wait_for_state(
                client,  # type: ignore[arg-type]
                page,  # type: ignore[arg-type]
                """(async () => {
                  if (typeof window.__MYRM_E2E_RUNTIME_READY__ === 'undefined') {
                    return { ready: false, phase: 'missing' };
                  }
                  try {
                    await window.__MYRM_E2E_RUNTIME_READY__;
                    return { ready: true };
                  } catch (error) {
                    return { ready: false, phase: 'error', error: String(error) };
                  }
                })()""",
                timeout_sec=min(45.0, max(5.0, remaining)),
            )
        else:
            source = e2e_runtime_binding_source(expected)
            if source:
                client.evaluate(  # type: ignore[attr-defined]
                    page,
                    f"(() => {{{source} return true; }})()",
                    timeout_sec=min(15.0, max(5.0, remaining)),
                )
            else:
                client.evaluate(  # type: ignore[attr-defined]
                    page,
                    e2e_api_base_inject_js(expected),
                    timeout_sec=min(15.0, max(5.0, remaining)),
                )
        time.sleep(0.5)
    raise AssertionError(
        f"SHPOIB API binding failed: expected {expected!r}, probe={last_probe!r}"
    )


def _assert_variant_ui(
    client: object,
    page: object,
    *,
    chat_id: str,
    variant: str,
    page_url: str,
) -> None:
    answer_json = json.dumps(_FIXTURE_ANSWER)
    message_ready_js = f"""(() => {{
      const target = {answer_json};
      const store = window.__myrmChatStore?.getState?.();
      const msg = (store?.messages || []).find(
        (item) => item.role === 'assistant' && (item.content || '').includes(target),
      );
      return {{ ready: !!msg, count: store?.messages?.length ?? 0 }};
    }})()"""

    api_base = get_e2e_api_url().rstrip("/")

    bridge_ready = wait_for_react_e2e_bridge(
        client,  # type: ignore[arg-type]
        page,  # type: ignore[arg-type]
        timeout_sec=_bridge_ready_timeout_sec(),
        page_url=page_url,
    )
    assert bridge_ready.get("ready") is True, json.dumps(
        bridge_ready, ensure_ascii=False
    )

    _ensure_shpoib_api_binding(
        client,
        page,
        api_base,
        timeout_sec=_attach_eval_timeout_sec(),
    )

    attached = client.evaluate(  # type: ignore[attr-defined]
        page,
        _attach_chat_probe(chat_id),
        timeout_sec=_attach_eval_timeout_sec(),
    )
    assert isinstance(attached, dict) and attached.get("ok") is True, attached

    dismiss_blocking_modals(client, page)  # type: ignore[arg-type]

    message_ready = wait_for_state(
        client,  # type: ignore[arg-type]
        page,  # type: ignore[arg-type]
        message_ready_js,
        timeout_sec=_attach_eval_timeout_sec(),
    )
    assert message_ready.get("ready") is True, json.dumps(
        message_ready, ensure_ascii=False
    )

    category_state = wait_for_state(
        client,  # type: ignore[arg-type]
        page,  # type: ignore[arg-type]
        _GUARDRAIL_CATEGORY_JS,
        timeout_sec=30.0,
    )
    assert category_state.get("ready") is True, (
        f"variant={variant} missing guardrail_blocked step: "
        f"{json.dumps(category_state, ensure_ascii=False)}"
    )

    answer_json = json.dumps(_FIXTURE_ANSWER)
    dom_answer_js = f"""(() => {{
      window.scrollTo(0, document.body.scrollHeight);
      const bodyText = document.body?.innerText || '';
      return {{
        ready: bodyText.includes({answer_json}),
        sample: bodyText.slice(0, 400),
      }};
    }})()"""
    dom_answer = wait_for_state(
        client,  # type: ignore[arg-type]
        page,  # type: ignore[arg-type]
        dom_answer_js,
        timeout_sec=_attach_eval_timeout_sec(),
    )
    assert dom_answer.get("ready") is True, json.dumps(
        dom_answer, ensure_ascii=False
    )

    client.evaluate(page, _EXPAND_PROGRESS_JS, timeout_sec=15.0)  # type: ignore[attr-defined]

    dom_ready = wait_for_state(
        client,  # type: ignore[arg-type]
        page,  # type: ignore[arg-type]
        _PROGRESS_DOM_READY_JS,
        timeout_sec=_attach_eval_timeout_sec(),
    )
    assert dom_ready.get("ready") is True, (
        f"variant={variant} progress UI not mounted: "
        f"{json.dumps(dom_ready, ensure_ascii=False)}"
    )

    badge_state = wait_for_state(
        client,  # type: ignore[arg-type]
        page,  # type: ignore[arg-type]
        _GUARDRAIL_BADGE_JS,
        timeout_sec=_attach_eval_timeout_sec(),
    )
    assert badge_state.get("ready") is True, (
        f"variant={variant} missing 安全拦截/Safety Blocked badge: "
        f"{json.dumps(badge_state, ensure_ascii=False)}"
    )


def _run_single_variant_ui_assertions(
    api_url: str, ui_url: str, *, variant: str, warm_route: bool = True
) -> None:
    seeded = _seed_fixture(api_url, variant=variant)
    chat_id = seeded["chat_id"]
    _ensure_fixture_assistant_ready(api_url, chat_id)
    if warm_route:
        warm_ui_route("/")
        warm_ui_route(f"/{chat_id}")

    target_url = f"{ui_url.rstrip('/')}/{chat_id}"
    with open_mcp_page(target_url, timeout_ms=120_000) as (client, page):
        ensure_desktop_viewport(client, page)
        dismiss_blocking_modals(client, page)
        client.evaluate(page, _DISMISS_MIGRATION_JS, timeout_sec=15.0)
        _assert_variant_ui(
            client, page, chat_id=chat_id, variant=variant, page_url=target_url
        )


@pytest.mark.parametrize("variant", _VARIANTS)
@pytest.mark.chrome_e2e(
    execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD"
)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_guardrail_bash_progress_step_and_safety_badge_render(variant: str) -> None:
    """Seed guardrail_blocked bash step per variant and assert UI Badge in Chrome."""
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(api_url)

    last_error: BaseException | None = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            _run_single_variant_ui_assertions(
                api_url, ui_url, variant=variant, warm_route=(attempt == 1)
            )
            return
        except Exception as exc:
            last_error = exc
            if attempt >= _MAX_ATTEMPTS or not _is_transport_retryable(exc):
                raise
            _force_mux_heal_before_retry()

    if last_error is not None:
        raise last_error
