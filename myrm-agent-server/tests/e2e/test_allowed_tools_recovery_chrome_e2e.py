"""Chrome READ E2E: allowed_tools recovery progress step + Trust Reduced badge."""

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

from tests.support.chrome_mcp_e2e import (
    _require_e2e_cdp_ready,  # noqa: E402
    dismiss_blocking_modals,
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_mcp_page,
    prepare_e2e_ui_session,
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


def _force_mux_heal_before_retry() -> None:
    _require_e2e_cdp_ready(budget_sec=45.0)
    from mux.attach_force_restart import force_mux_attach_restart_scoped

    force_mux_attach_restart_scoped(reason="allowed_tools recovery outer retry")
    time.sleep(3.0)


def _is_transport_retryable(exc: BaseException) -> bool:
    text = str(exc)
    return any(marker in text for marker in _TRANSPORT_RETRY_MARKERS)


def _seed_fixture(api_url: str) -> dict[str, str]:
    seeded = http_json(
        "POST",
        f"{api_url}/api/v1/chats/test/seed-allowed-tools-recovery-fixture",
    )
    assert isinstance(seeded, dict)
    chat_id = str(seeded.get("chat_id") or "")
    assert chat_id.startswith("e2eallowed")
    return {"chat_id": chat_id}


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
      if (key === 'allowed_tools_rejected_recovery') {
        return { ready: true, step_key: key, status: step.status || null };
      }
    }
  }
  return { ready: false, msg_count: msgs.length };
})()"""


_TRUST_CATEGORY_JS = """(() => {
  const store = window.__myrmChatStore?.getState?.();
  const msgs = store?.messages || [];
  for (const msg of msgs) {
    const metaSteps = Array.isArray(msg.metadata?.progressSteps)
      ? msg.metadata.progressSteps
      : [];
    const steps = (msg.progressSteps?.length ? msg.progressSteps : metaSteps) || [];
    for (const step of steps) {
      if (String(step.error_category || '') === 'trust_attenuation') {
        return { ready: true, step_key: step.step_key || step.tool_name || null };
      }
    }
  }
  return { ready: false, msg_count: msgs.length };
})()"""


_TRUST_BADGE_JS = """(() => {
  const panel = document.querySelector('[data-testid="progress-steps-panel"]');
  if (!panel) {
    return { ready: false, err: 'no-panel' };
  }
  const text = panel.textContent || '';
  const hasRecovery =
    text.includes('Gateway adjusted tool policy and retried') ||
    text.includes('网关已自动调整工具策略并重试');
  const hasTrustBadge =
    text.includes('Trust Reduced') || text.includes('信任降级');
  return {
    ready: hasRecovery && hasTrustBadge,
    hasRecovery,
    hasTrustBadge,
    text_head: text.slice(0, 500),
  };
})()"""


_EXPAND_PROGRESS_JS = """(() => {
  const toggle = document.querySelector('[data-testid="progress-steps-toggle"]');
  if (!toggle) return { ok: false, err: 'no-toggle' };
  toggle.click();
  return { ok: true };
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


_FIXTURE_ANSWER = "Allowed tools recovery Chrome E2E fixture answer."


def _run_read_ui_assertions(api_url: str, ui_url: str, chat_id: str) -> None:
    warm_ui_route(f"/{chat_id}")
    answer_json = json.dumps(_FIXTURE_ANSWER)
    message_ready_js = f"""(() => {{
      const target = {answer_json};
      const store = window.__myrmChatStore?.getState?.();
      const msg = (store?.messages || []).find(
        (item) => item.role === 'assistant' && (item.content || '').includes(target),
      );
      return {{ ready: !!msg, count: store?.messages?.length ?? 0 }};
    }})()"""

    with open_mcp_page(f"{ui_url}/{chat_id}", timeout_ms=120_000) as (client, page):
        client.evaluate(page, _DISMISS_MIGRATION_JS, timeout_sec=15.0)

        attached = client.evaluate(
            page,
            _attach_chat_probe(chat_id),
            timeout_sec=90.0,
        )
        assert isinstance(attached, dict) and attached.get("ok") is True, attached

        dismiss_blocking_modals(client, page)

        message_ready = wait_for_state(
            client,
            page,
            message_ready_js,
            timeout_sec=90.0,
        )
        assert message_ready.get("ready") is True, json.dumps(
            message_ready, ensure_ascii=False
        )

        step_state = wait_for_state(
            client,
            page,
            _RECOVERY_STEP_JS,
            timeout_sec=30.0,
        )
        assert step_state.get("ready") is True, json.dumps(
            step_state, ensure_ascii=False
        )

        trust_state = wait_for_state(
            client,
            page,
            _TRUST_CATEGORY_JS,
            timeout_sec=30.0,
        )
        assert trust_state.get("ready") is True, json.dumps(
            trust_state, ensure_ascii=False
        )

        expanded = client.evaluate(page, _EXPAND_PROGRESS_JS, timeout_sec=15.0)
        assert isinstance(expanded, dict) and expanded.get("ok") is True, expanded

        badge_state = wait_for_state(
            client,
            page,
            _TRUST_BADGE_JS,
            timeout_sec=30.0,
        )
        assert badge_state.get("ready") is True, json.dumps(
            badge_state, ensure_ascii=False
        )


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_allowed_tools_recovery_progress_step_and_trust_badge_render() -> None:
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
