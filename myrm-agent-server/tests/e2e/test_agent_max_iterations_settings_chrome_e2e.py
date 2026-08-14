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
  const bodyLength = (document.body?.innerText || '').length;
  if (!tab) {
    return { ready: false, reason: 'no-capabilities-tab', bodyLength };
  }
  tab.click();
  return new Promise(resolve => setTimeout(() => {
    const headings = Array.from(document.querySelectorAll('label, h3'));
    const heading = headings.find((el) => /Max Iterations|最大迭代次数|最大疊代次數/.test(el.textContent || ''));
    if (!heading) {
      return resolve({
        ready: false,
        reason: 'no-max-iterations-heading',
        bodyLength,
        snippet: (document.body.innerText || '').slice(0, 300),
      });
    }
    const card = heading.closest('div.rounded-xl') || heading.parentElement;
    const input = card ? card.querySelector('input[type="number"]') : null;
    if (!input) {
      return resolve({ ready: false, reason: 'no-number-input', bodyLength });
    }
    resolve({
      ready: true,
      value: input.value,
      min: input.min,
      max: input.max,
      placeholder: input.placeholder,
      bodyLength,
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
    """Returns an evaluate expression that sets the Max Iterations input to a value.

    Uses the native HTMLInputElement value setter (the React Testing Library
    approach) plus an InputEvent so React 19 controlled components observe the
    change, and reports the agent Save button state after the change so tests
    can confirm React state actually updated.
    """
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
      const raw = String({json.dumps(expected_value)});
      setter.set.call(input, raw);
      input.dispatchEvent(new InputEvent('input', {{ bubbles: true, data: raw }}));
      input.dispatchEvent(new Event('change', {{ bubbles: true }}));
      return new Promise(resolve => setTimeout(() => {{
        const section = document.querySelector('[data-section="agents"]') || document.body;
        const saveBtn = Array.from(section.querySelectorAll('button')).find((b) =>
          /^(Save|保存|儲存)$/i.test((b.textContent || '').trim()) && b.offsetParent !== null,
        );
        resolve({{
          ok: true,
          value: input.value,
          saveDisabled: saveBtn ? saveBtn.disabled : null,
          hasValueTracker: !!input._valueTracker,
        }});
      }}, 300));
    }})()"""

# Clicks the Save button on the agent preview card (text matches any locale).
# Scoped to the active agents section and only visible buttons so hidden
# sibling sections (SettingsLayout keeps visited tabs mounted with `hidden`)
# can never be mis-targeted. Returns ready/bodyLength so wait_for_state does
# not treat the page as blank and trigger a healing reload that wipes state.
_CLICK_SAVE_JS = """(() => {
  const section = document.querySelector('[data-section="agents"]') || document.body;
  const matches = Array.from(section.querySelectorAll('button')).filter((btn) =>
    /^(Save|保存|儲存)$/i.test((btn.textContent || '').trim()) && btn.offsetParent !== null,
  );
  const save = matches.find((btn) => !btn.disabled);
  const bodyLength = (document.body?.innerText || '').length;
  const list = matches.map((b) => ({
    text: (b.textContent || '').trim(),
    disabled: b.disabled,
  }));
  if (!save) {
    return { ready: false, reason: 'no-enabled-visible-save-button', list, bodyLength };
  }
  save.click();
  return { ready: true, clicked: (save.textContent || '').trim(), list, bodyLength };
})()"""

# Wraps window.fetch to record PUT bodies for the agent endpoint (diagnostic).
_INSTALL_FETCH_TAP_JS = """(() => {
  if (window.__diag_fetch_tap__) return { ok: true };
  window.__diag_put_bodies__ = [];
  const orig = window.fetch.bind(window);
  window.fetch = async (...args) => {
    const [url, opts] = args;
    try {
      if (/\\/api\\/v1\\/user-agents\\/[^/]+$/.test(String(url)) && (opts?.method === 'PUT')) {
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
    .map((b) => ({
      text: (b.textContent || '').trim(),
      disabled: b.disabled,
      visible: b.offsetParent !== null,
      section: b.closest('[data-section]')?.getAttribute('data-section') ?? null,
    })),
}))()"""

# Save completion probe: after a successful save the editor sets hasChanges=false and
# saving=false, so the Save button is re-disabled and its loading spinner is gone.
# Scoped to the visible agent editor Save button only.
_SAVE_COMPLETE_JS = """(() => {
  const section = document.querySelector('[data-section="agents"]') || document.body;
  const buttons = Array.from(section.querySelectorAll('button'));
  const save = buttons.find((btn) =>
    /^(Save|保存|儲存)$/i.test((btn.textContent || '').trim()) && btn.offsetParent !== null,
  );
  const bodyLength = (document.body?.innerText || '').length;
  if (!save) return { ready: false, reason: 'no-visible-save-button', bodyLength };
  const hasSpinner = !!save.querySelector('.animate-spin');
  return {
    ready: save.disabled && !hasSpinner,
    disabled: save.disabled,
    hasSpinner,
    bodyLength,
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
    api_url: str, agent_id: str, expected: int | None, *, timeout_sec: float = 30.0, diag: str = ""
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
            assert set_res.get("saveDisabled") is False, (
                "React state must update so the agent Save button unlocks "
                f"(saveDisabled={set_res.get('saveDisabled')})"
            )

            client.evaluate(page, _INSTALL_FETCH_TAP_JS, timeout_sec=15.0)
            clicked = wait_for_state(
                client,
                page,
                _CLICK_SAVE_JS,
                timeout_sec=_warm_ui_parallel_wait_sec(20.0),
            )
            assert isinstance(clicked, dict) and clicked.get("ready") is True, clicked

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


# Clears the Max Iterations input through the native setter so React's onChange
# receives '' and maps it to null (restore system default). Reports the Save
# button state so tests confirm React state actually updated.
def _clear_max_iterations_js() -> str:
    return """(() => {
      const headings = Array.from(document.querySelectorAll('label, h3'));
      const heading = headings.find((el) => /Max Iterations|最大迭代次数|最大疊代次數/.test(el.textContent || ''));
      if (!heading) return { ok: false, reason: 'no-heading' };
      const card = heading.closest('div.rounded-xl') || heading.parentElement;
      const input = card ? card.querySelector('input[type="number"]') : null;
      if (!input) return { ok: false, reason: 'no-input' };
      const setter = Object.getOwnPropertyDescriptor(
        Object.getPrototypeOf(input), 'value',
      );
      setter.set.call(input, '');
      input.dispatchEvent(new InputEvent('input', { bubbles: true, data: '' }));
      input.dispatchEvent(new Event('change', { bubbles: true }));
      return new Promise(resolve => setTimeout(() => {
        const section = document.querySelector('[data-section="agents"]') || document.body;
        const saveBtn = Array.from(section.querySelectorAll('button')).find((b) =>
          /^(Save|保存|儲存)$/i.test((b.textContent || '').trim()) && b.offsetParent !== null,
        );
        resolve({
          ok: true,
          value: input.value,
          saveDisabled: saveBtn ? saveBtn.disabled : null,
        });
      }, 300));
    })()"""


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="STANDARD",
    private_reason="exclusive_backend",
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_agent_max_iterations_clear_resets_to_default_via_ui() -> None:
    """Clearing the Max Iterations input must send an explicit null and reset the
    stored value back to the system default (DB NULL). Regression for the
    ``is not None`` guard that silently ignored explicit null resets."""
    api_url = get_e2e_api_url()
    prepare_e2e_ui_session(api_url)

    name = f"clear-e2e-{uuid.uuid4().hex[:8]}"
    agent_id = _create_agent(api_url, name=name)
    try:
        # Seed a concrete value through the backend so the reset has something
        # to clear (the fresh-agent default is already NULL).
        seed = http_json(
            "PUT", f"{api_url}/api/v1/user-agents/{agent_id}", {"max_iterations": 50}
        )
        assert (seed.get("data") or {}).get("max_iterations") == 50, seed
        assert _fetch_max_iterations(api_url, agent_id) == 50

        warm_ui_route("/settings")
        edit_url = f"{get_e2e_ui_url().rstrip('/')}{_EDIT_URL}{agent_id}"
        with open_settings_subroute(
            edit_url.replace(get_e2e_ui_url().rstrip("/"), ""),
            timeout_ms=120_000,
        ) as (client, page):
            client.evaluate(page, _DISMISS_MIGRATION_JS, timeout_sec=15.0)
            dismiss_blocking_modals(client, page)

            # Wait for the editor to load the seeded value.
            probe = wait_for_state(
                client,
                page,
                _CAPABILITIES_INPUT_JS,
                timeout_sec=_warm_ui_parallel_wait_sec(60.0),
            )
            assert probe.get("ready") is True, json.dumps(
                probe, indent=2, ensure_ascii=False
            )
            assert probe.get("value") == "50", (
                f"editor must render seeded max_iterations, got {probe.get('value')}"
            )

            # Clear the input -> React maps '' to null -> Save unlocks.
            clear_res = client.evaluate(page, _clear_max_iterations_js(), timeout_sec=15.0)
            assert isinstance(clear_res, dict) and clear_res.get("ok") is True, clear_res
            assert str(clear_res.get("value")) == "", clear_res
            assert clear_res.get("saveDisabled") is False, (
                "clearing the field must mark the agent dirty so Save unlocks "
                f"(saveDisabled={clear_res.get('saveDisabled')})"
            )

            client.evaluate(page, _INSTALL_FETCH_TAP_JS, timeout_sec=15.0)
            clicked = wait_for_state(
                client,
                page,
                _CLICK_SAVE_JS,
                timeout_sec=_warm_ui_parallel_wait_sec(20.0),
            )
            assert isinstance(clicked, dict) and clicked.get("ready") is True, clicked

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

        # The explicit null must reach the backend and reset to default.
        _wait_max_iterations(
            api_url, agent_id, expected=None, timeout_sec=30.0,
            diag=json.dumps(diag, ensure_ascii=False),
        )
    finally:
        http_json("DELETE", f"{api_url}/api/v1/user-agents/{agent_id}")
