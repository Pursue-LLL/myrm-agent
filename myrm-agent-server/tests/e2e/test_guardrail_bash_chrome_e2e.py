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
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_mcp_page,
    prepare_e2e_ui_session,
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
    "no-panel",
)


def _force_mux_heal_before_retry() -> None:
    _require_e2e_cdp_ready(budget_sec=45.0)
    from mux_attach_force_restart import force_mux_attach_restart_scoped

    force_mux_attach_restart_scoped(reason="guardrail bash outer retry")
    time.sleep(3.0)


def _is_transport_retryable(exc: BaseException) -> bool:
    text = str(exc)
    return any(marker in text for marker in _TRANSPORT_RETRY_MARKERS)


def _seed_fixture(api_url: str, *, variant: str) -> dict[str, str]:
    seeded = http_json(
        "POST",
        f"{api_url}/api/v1/chats/test/seed-guardrail-bash-fixture?variant={variant}",
    )
    assert isinstance(seeded, dict)
    chat_id = str(seeded.get("chat_id") or "")
    assert chat_id.startswith("e2eguard")
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
    text_head: text.slice(0, 600),
  };
})()"""


_PROGRESS_DOM_READY_JS = """(() => {
  const toggle = document.querySelector('[data-testid="progress-steps-toggle"]');
  const panel = document.querySelector('[data-testid="progress-steps-panel"]');
  return {
    ready: !!(toggle || panel),
    hasToggle: !!toggle,
    hasPanel: !!panel,
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


def _assert_variant_ui(
    client: object,
    page: object,
    *,
    chat_id: str,
    variant: str,
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

    attached = client.evaluate(page, _attach_chat_probe(chat_id), timeout_sec=90.0)  # type: ignore[attr-defined]
    assert isinstance(attached, dict) and attached.get("ok") is True, attached

    dismiss_blocking_modals(client, page)  # type: ignore[arg-type]

    message_ready = wait_for_state(
        client,  # type: ignore[arg-type]
        page,  # type: ignore[arg-type]
        message_ready_js,
        timeout_sec=90.0,
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

    dom_ready = wait_for_state(
        client,  # type: ignore[arg-type]
        page,  # type: ignore[arg-type]
        _PROGRESS_DOM_READY_JS,
        timeout_sec=45.0,
    )
    assert dom_ready.get("ready") is True, (
        f"variant={variant} progress UI not mounted: "
        f"{json.dumps(dom_ready, ensure_ascii=False)}"
    )

    expanded = client.evaluate(page, _EXPAND_PROGRESS_JS, timeout_sec=15.0)  # type: ignore[attr-defined]
    if not (isinstance(expanded, dict) and expanded.get("ok") is True):
        # Toggle/panel may mount late under parallel mux; badge poll expands inline.
        pass

    badge_state = wait_for_state(
        client,  # type: ignore[arg-type]
        page,  # type: ignore[arg-type]
        _GUARDRAIL_BADGE_JS,
        timeout_sec=45.0,
    )
    assert badge_state.get("ready") is True, (
        f"variant={variant} missing 安全拦截/Safety Blocked badge: "
        f"{json.dumps(badge_state, ensure_ascii=False)}"
    )


def _run_single_variant_ui_assertions(
    api_url: str, ui_url: str, *, variant: str
) -> None:
    seeded = _seed_fixture(api_url, variant=variant)
    chat_id = seeded["chat_id"]
    warm_ui_route(f"/{chat_id}")

    with open_mcp_page(f"{ui_url}/{chat_id}", timeout_ms=120_000) as (client, page):
        client.evaluate(page, _DISMISS_MIGRATION_JS, timeout_sec=15.0)
        _assert_variant_ui(client, page, chat_id=chat_id, variant=variant)


@pytest.mark.parametrize("variant", _VARIANTS)
@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE", access_scope="NAMESPACE_WRITE", workload="STANDARD"
)
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
            _run_single_variant_ui_assertions(api_url, ui_url, variant=variant)
            return
        except Exception as exc:
            last_error = exc
            if attempt >= _MAX_ATTEMPTS or not _is_transport_retryable(exc):
                raise
            _force_mux_heal_before_retry()

    if last_error is not None:
        raise last_error
