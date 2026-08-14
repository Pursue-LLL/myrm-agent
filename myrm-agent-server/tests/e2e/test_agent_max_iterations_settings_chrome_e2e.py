"""Chrome E2E: user edits "Max Iterations" in the agent Capabilities tab and it persists.

Prerequisites:
  ./myrm isolate <id> ready --chrome

Covers item#1 "Per-Agent Recursion Limit" front-end chain end to end:
  T1 - Settings > Agents opens the agent editor for a seeded agent.
  T2 - The Capabilities tab exposes the "Max Iterations" number input with backend bounds (min=5, max=500).
  T3 - Editing the value and clicking Save persists max_iterations through PUT (asserted via GET API).
  T4 - Cleanup removes the seeded agent.

The runtime recursion-limit behavior (iteration_limit_reached SSE) is covered separately by
tests/api/agent/test_max_iterations_live_e2e.py against the real LLM path.
"""

from __future__ import annotations

import json
import time
import uuid

import pytest

from tests.support.chrome_mcp_e2e import (
    _warm_ui_parallel_wait_sec,
    dismiss_blocking_modals,
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_settings_subroute,
    prepare_e2e_ui_session,
    wait_for_state,
    warm_ui_route,
)

_EDIT_URL = "/settings/agents?agentId="

_DISMISS_MIGRATION_JS = """(() => {
  try {
    sessionStorage.setItem('migration_discovery_dismissed', 'true');
    sessionStorage.setItem('competitor_migration_dismissed', 'true');
  } catch (err) {
    return { ok: false, err: String(err) };
  }
  return { ok: true };
})()"""

# Switches to the Capabilities tab and locates the "Max Iterations" number input.
_CAPABILITIES_INPUT_JS = """(() => {
  const tab = document.querySelector('[data-testid="agent-tab-capabilities"]');
  if (!tab) {
    return { ready: false, reason: 'no-capabilities-tab' };
  }
  tab.click();
  return new Promise(resolve => setTimeout(() => {
    const headings = Array.from(document.querySelectorAll('label, h3'));
    const heading = headings.find((el) => /Max Iterations|最大迭代次数|最大疊代次數/.test(el.textContent || ''));
    if (!heading) {
      return resolve({
        ready: false,
        reason: 'no-max-iterations-heading',
        snippet: (document.body.innerText || '').slice(0, 300),
      });
    }
    const card = heading.closest('div.rounded-xl') || heading.parentElement;
    const input = card ? card.querySelector('input[type="number"]') : null;
    if (!input) {
      return resolve({ ready: false, reason: 'no-number-input' });
    }
    resolve({
      ready: true,
      value: input.value,
      min: input.min,
      max: input.max,
      placeholder: input.placeholder,
    });
  }, 300));
})()"""

# Sets the number input through the native setter so React's onChange fires.
# The expected value is embedded at call time (evaluate only accepts expression + timeout).
_SET_MAX_ITERATIONS_JS = """(expectedValue) => {
  const headings = Array.from(document.querySelectorAll('label, h3'));
  const heading = headings.find((el) => /Max Iterations|最大迭代次数|最大疊代次數/.test(el.textContent || ''));
  if (!heading) {
    return { ok: false, reason: 'no-heading' };
  }
  const card = heading.closest('div.rounded-xl') || heading.parentElement;
  const input = card ? card.querySelector('input[type="number"]') : null;
  if (!input) {
    return { ok: false, reason: 'no-input' };
  }
  const setter = Object.getOwnPropertyDescriptor(
    Object.getPrototypeOf(input), 'value',
  );
  setter.set.call(input, String(expectedValue));
  input.dispatchEvent(new Event('input', { bubbles: true }));
  return new Promise(resolve => setTimeout(() => {
    resolve({ ok: true, value: input.value });
  }, 200));
}"""


def _set_max_iterations_js(expected_value: int) -> str:
    """Returns an evaluate expression that sets the Max Iterations input to a value."""
    return f"""(() => {{
      const headings = Array.from(document.querySelectorAll('label, h3'));
      const heading = headings.find((el) => /Max Iterations|最大迭代次数|最大疊代次數/.test(el.textContent || ''));
      if (!heading) return {{ ok: false, reason: 'no-heading' }};
      const card = heading.closest('div.rounded-xl') || heading.parentElement;
      const input = card ? card.querySelector('input[type="number"]') : null;
      if (!input) return {{ ok: false, reason: 'no-input' }};
      const setter = Object.getOwnPropertyDescriptor(
        Object.getPrototypeOf(input), 'value',
      );
      setter.set.call(input, String({json.dumps(expected_value)}));
      input.dispatchEvent(new Event('input', {{ bubbles: true }}));
      return new Promise(resolve => setTimeout(() => {{
        resolve({{ ok: true, value: input.value }});
      }}, 200));
    }})()"""

# Clicks the Save button on the agent preview card (text matches any locale).
_CLICK_SAVE_JS = """(() => {
  const buttons = Array.from(document.querySelectorAll('button'));
  const matches = buttons.filter((btn) =>
    /^(Save|保存|儲存)$/i.test((btn.textContent || '').trim()),
  );
  const save = matches.find((btn) => !btn.disabled);
  const list = matches.map((b) => ({
    text: (b.textContent || '').trim(),
    disabled: b.disabled,
  }));
  if (!save) {
    return { ok: false, reason: 'no-enabled-save-button', list };
  }
  save.click();
  return { ok: true, clicked: (save.textContent || '').trim(), list };
})()"""

# Wraps window.fetch to record PUT bodies for the agent endpoint (diagnostic).
_INSTALL_FETCH_TAP_JS = """(() => {
  if (window.__diag_fetch_tap__) return { ok: true };
  window.__diag_put_bodies__ = [];
  const orig = window.fetch.bind(window);
  window.fetch = async (...args) => {
    const [url, opts] = args;
    try {
      if (/\/api\/v1\/user-agents\/[^/]+$/.test(String(url)) && (opts?.method === 'PUT')) {
        window.__diag_put_bodies__.push({
          url: String(url),
          body: opts.body ? String(opts.body) : null,
        });
      }
    } catch (err) { /* never break fetch */ }
    return orig(...args);
  };
  window.__diag_fetch_tap__ = true;
  return { ok: true };
})()"""

# Dumps diagnostics collected during the save flow.
_DIAG_DUMP_JS = """(() => ({
  apiBase: window.__MYRM_E2E_API_BASE__ ?? window.__MYRM_E2E_RUNTIME__?.apiBase ?? null,
  putBodies: window.__diag_put_bodies__ ?? [],
  allSaveButtons: Array.from(document.querySelectorAll('button'))
    .filter((b) => /^(Save|保存|儲存)$/i.test((b.textContent || '').trim()))
    .map((b) => ({ text: (b.textContent || '').trim(), disabled: b.disabled })),
}))()"""

# Save completion probe: after a successful save the editor sets hasChanges=false and
# saving=false, so the Save button is re-disabled and its loading spinner is gone.
_SAVE_COMPLETE_JS = """(() => {
  const buttons = Array.from(document.querySelectorAll('button'));
  const save = buttons.find((btn) =>
    /^(Save|保存|儲存)$/i.test((btn.textContent || '').trim()),
  );
  if (!save) return { ready: false, reason: 'no-save-button' };
  const hasSpinner = !!save.querySelector('.animate-spin');
  return {
    ready: save.disabled && !hasSpinner,
    disabled: save.disabled,
    hasSpinner,
  };
})()"""


def _create_agent(api_url: str, *, name: str) -> str:
    resp = http_json("POST", f"{api_url}/api/v1/user-agents", {"name": name})
    data = resp["data"]
    agent_id = data.get("id") or data.get("agent_id")
    assert isinstance(agent_id, str) and agent_id, json.dumps(data, ensure_ascii=False)
    return agent_id


def _fetch_max_iterations(api_url: str, agent_id: str) -> int | None:
    resp = http_json("GET", f"{api_url}/api/v1/user-agents/{agent_id}")
    return (resp.get("data") or {}).get("max_iterations")


def _wait_max_iterations(
    api_url: str, agent_id: str, expected: int, *, timeout_sec: float = 30.0, diag: str = ""
) -> None:
    deadline = time.monotonic() + timeout_sec
    last: int | None = None
    while time.monotonic() < deadline:
        last = _fetch_max_iterations(api_url, agent_id)
        if last == expected:
            return
        time.sleep(1.0)
    raise AssertionError(
        f"max_iterations did not persist: expected={expected} last={last}\n"
        f"diag: {diag}"
    )


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="STANDARD",
    private_reason="exclusive_backend",
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_agent_max_iterations_edit_persists_via_ui() -> None:
    """Max Iterations edited in the Capabilities tab must persist through the real UI save path."""
    api_url = get_e2e_api_url()
    prepare_e2e_ui_session(api_url)

    name = f"lim-e2e-{uuid.uuid4().hex[:8]}"
    agent_id = _create_agent(api_url, name=name)
    try:
        assert _fetch_max_iterations(api_url, agent_id) is None, (
            "fresh agent must start with default max_iterations"
        )

        warm_ui_route("/settings")
        edit_url = f"{get_e2e_ui_url().rstrip('/')}{_EDIT_URL}{agent_id}"
        with open_settings_subroute(
            edit_url.replace(get_e2e_ui_url().rstrip("/"), ""),
            timeout_ms=120_000,
        ) as (client, page):
            client.evaluate(page, _DISMISS_MIGRATION_JS, timeout_sec=15.0)
            dismiss_blocking_modals(client, page)

            # T1/T2: capabilities tab + bounds on the Max Iterations input.
            probe = wait_for_state(
                client,
                page,
                _CAPABILITIES_INPUT_JS,
                timeout_sec=_warm_ui_parallel_wait_sec(60.0),
            )
            assert probe.get("ready") is True, json.dumps(
                probe, indent=2, ensure_ascii=False
            )
            assert probe.get("min") == "5", f"input min mismatch: {probe}"
            assert probe.get("max") == "500", f"input max mismatch: {probe}"

            # T3: edit value via native setter, then save.
            set_res = client.evaluate(
                page, _set_max_iterations_js(50), timeout_sec=15.0
            )
            assert isinstance(set_res, dict) and set_res.get("ok") is True, set_res
            assert str(set_res.get("value")) == "50", set_res

            client.evaluate(page, _INSTALL_FETCH_TAP_JS, timeout_sec=15.0)
            clicked = client.evaluate(page, _CLICK_SAVE_JS, timeout_sec=15.0)
            assert isinstance(clicked, dict) and clicked.get("ok") is True, clicked

            saved = wait_for_state(
                client,
                page,
                _SAVE_COMPLETE_JS,
                timeout_sec=_warm_ui_parallel_wait_sec(30.0),
            )
            assert saved.get("ready") is True, json.dumps(
                saved, indent=2, ensure_ascii=False
            )
            diag = client.evaluate(page, _DIAG_DUMP_JS, timeout_sec=15.0)

        # Persistence truth: the value must reach the backend.
        _wait_max_iterations(
            api_url, agent_id, expected=50, timeout_sec=30.0,
            diag=json.dumps(diag, ensure_ascii=False),
        )
    finally:
        http_json("DELETE", f"{api_url}/api/v1/user-agents/{agent_id}")
