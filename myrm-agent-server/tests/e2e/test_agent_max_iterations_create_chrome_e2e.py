"""Chrome E2E: create a brand-new agent through the real WebUI and persist max_iterations.

Covers the item#1 "Per-Agent Recursion Limit" full creation path that the
edit-only test (`test_agent_max_iterations_edit_persists_via_ui`) does not:
  T1 - Settings > Agents > "Create Agent" (``?new=true``) opens the empty editor.
  T2 - The Capabilities tab exposes the "Max Iterations" number input (5..500).
  T3 - Filling the name, setting max_iterations and clicking Save creates the
       agent through POST /api/v1/user-agents with the value embedded.
  T4 - The UI navigates to ``?agentId=`` and re-renders max_iterations from the
       backend; the API GET confirms persistence.
  T5 - Cleanup removes the created agent.

Prerequisite:
  ./myrm isolate <id> ready --chrome
"""

from __future__ import annotations

import json
import re
import time
import uuid

import pytest

from tests.support.chrome_mcp_e2e import (
    _warm_ui_parallel_wait_sec,
    dismiss_blocking_modals,
    get_e2e_api_url,
    http_json,
    open_settings_subroute,
    prepare_e2e_ui_session,
    wait_for_state,
    warm_ui_route,
)

_DISMISS_MIGRATION_JS = """(() => {
  try {
    sessionStorage.setItem('migration_discovery_dismissed', 'true');
    sessionStorage.setItem('competitor_migration_dismissed', 'true');
  } catch (err) {
    return { ok: false, err: String(err) };
  }
  return { ok: true };
})()"""

# The empty create-agent editor is ready once the name input is visible.
_NEW_AGENT_FORM_READY_JS = """(() => {
  const bodyLength = (document.body?.innerText || '').length;
  const section = document.querySelector('[data-section="agents"]') || document.body;
  const inputs = Array.from(section.querySelectorAll('input'));
  const nameInput = inputs.find((el) =>
    el.placeholder && /Enter agent name|输入智能体名称/.test(el.placeholder),
  );
  if (!nameInput) {
    return { ready: false, reason: 'no-name-input', bodyLength };
  }
  const heading = Array.from(document.querySelectorAll('h1, h2, h3')).find((el) =>
    /Create Agent|创建智能体/.test(el.textContent || ''),
  );
  return {
    ready: true,
    hasCreateHeading: !!heading,
    namePlaceholder: nameInput.placeholder,
    nameValue: nameInput.value,
    bodyLength,
  };
})()"""

# Switches to the Capabilities tab and locates the Max Iterations number input.
_CAPABILITIES_INPUT_JS = """(() => {
  const tab = document.querySelector('[data-testid="agent-tab-capabilities"]');
  const bodyLength = (document.body?.innerText || '').length;
  if (!tab) {
    return { ready: false, reason: 'no-capabilities-tab', bodyLength };
  }
  tab.click();
  return new Promise(resolve => setTimeout(() => {
    const headings = Array.from(document.querySelectorAll('label, h3'));
    const heading = headings.find((el) => /Max Iterations|最大迭代次数/.test(el.textContent || ''));
    if (!heading) {
      return resolve({ ready: false, reason: 'no-max-iterations-heading', bodyLength });
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
      bodyLength,
    });
  }, 300));
})()"""


def _set_agent_name_js(name: str) -> str:
    """Set the agent name through the native setter so React onChange fires."""
    return f"""(() => {{
      const section = document.querySelector('[data-section="agents"]') || document.body;
      const input = Array.from(section.querySelectorAll('input')).find((el) =>
        el.placeholder && /Enter agent name|输入智能体名称/.test(el.placeholder),
      );
      if (!input) return {{ ok: false, reason: 'no-name-input' }};
      const setter = Object.getOwnPropertyDescriptor(
        Object.getPrototypeOf(input), 'value',
      );
      const raw = {json.dumps(name)};
      setter.set.call(input, raw);
      input.dispatchEvent(new InputEvent('input', {{ bubbles: true, data: raw }}));
      input.dispatchEvent(new Event('change', {{ bubbles: true }}));
      return new Promise(resolve => setTimeout(() => {{
        const section2 = document.querySelector('[data-section="agents"]') || document.body;
        const saveBtn = Array.from(section2.querySelectorAll('button')).find((b) =>
          /^(Save|保存|儲存)$/i.test((b.textContent || '').trim()) && b.offsetParent !== null,
        );
        resolve({{
          ok: true,
          value: input.value,
          saveDisabled: saveBtn ? saveBtn.disabled : null,
        }});
      }}, 300));
    }})()"""


def _set_max_iterations_js(expected_value: int) -> str:
    """Set the Max Iterations input via native setter + InputEvent, and report
    the agent Save button state so tests confirm React state updated."""
    return f"""(() => {{
      const headings = Array.from(document.querySelectorAll('label, h3'));
      const heading = headings.find((el) => /Max Iterations|最大迭代次数/.test(el.textContent || ''));
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
        }});
      }}, 300));
    }})()"""


def _click_save_js() -> str:
    """Click the visible enabled Save button in the agents section."""
    return """(() => {
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


# Wraps window.fetch to record POST bodies for the user-agents endpoint (diagnostic).
_INSTALL_FETCH_TAP_JS = """(() => {
  if (window.__diag_fetch_tap__) return { ok: true };
  window.__diag_post_bodies__ = [];
  const orig = window.fetch.bind(window);
  window.fetch = async (...args) => {
    const [url, opts] = args;
    try {
      if (/\\/api\\/v1\\/user-agents\\/?$/.test(String(url)) && (opts?.method === 'POST')) {
        window.__diag_post_bodies__.push({
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


# After a successful create the UI router.replace()s to ?agentId= and the editor
# reloads the agent, re-rendering max_iterations from the backend. This probe
# treats both facts as the "creation completed" signal.
_CREATION_COMPLETE_JS = """(() => {
  const bodyLength = (document.body?.innerText || '').length;
  const url = location.href;
  const m = url.match(/[?&]agentId=([0-9a-zA-Z_-]+)/);
  if (!m) return { ready: false, reason: 'no-agentId', url, bodyLength };
  const headings = Array.from(document.querySelectorAll('label, h3'));
  const heading = headings.find((el) => /Max Iterations|最大迭代次数/.test(el.textContent || ''));
  if (!heading) return { ready: false, reason: 'no-max-iterations-heading', url, bodyLength };
  const card = heading.closest('div.rounded-xl') || heading.parentElement;
  const input = card ? card.querySelector('input[type="number"]') : null;
  if (!input) return { ready: false, reason: 'no-number-input', url, bodyLength };
  return { ready: true, value: input.value, agentId: m[1], url, bodyLength };
})()"""


def _fetch_max_iterations(api_url: str, agent_id: str) -> int | None:
    resp = http_json("GET", f"{api_url}/api/v1/user-agents/{agent_id}")
    return (resp.get("data") or {}).get("max_iterations")


def _wait_max_iterations(
    api_url: str,
    agent_id: str,
    expected: int,
    *,
    timeout_sec: float = 30.0,
    diag: str = "",
) -> None:
    deadline = time.monotonic() + timeout_sec
    last: int | None = None
    while time.monotonic() < deadline:
        last = _fetch_max_iterations(api_url, agent_id)
        if last == expected:
            return
        time.sleep(1.0)
    raise AssertionError(f"max_iterations did not persist: expected={expected} last={last}\ndiag: {diag}")


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="STANDARD",
    private_reason="exclusive_backend",
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_create_agent_with_max_iterations_via_ui() -> None:
    """A user can create a fresh agent in the WebUI and set max_iterations in the
    same flow — the value must be written on create and survive the round-trip."""
    api_url = get_e2e_api_url()
    prepare_e2e_ui_session(api_url)

    name = f"create-e2e-{uuid.uuid4().hex[:8]}"
    try:
        warm_ui_route("/settings")
        with open_settings_subroute(
            "/settings/agents?new=true",
            timeout_ms=120_000,
        ) as (client, page):
            client.evaluate(page, _DISMISS_MIGRATION_JS, timeout_sec=15.0)
            dismiss_blocking_modals(client, page)

            # T1: the empty create-agent editor is ready.
            form = wait_for_state(
                client,
                page,
                _NEW_AGENT_FORM_READY_JS,
                timeout_sec=_warm_ui_parallel_wait_sec(60.0),
            )
            assert form.get("ready") is True, json.dumps(form, indent=2, ensure_ascii=False)

            # T1b: fill the agent name so hasChanges flips and Save unlocks.
            name_res = client.evaluate(page, _set_agent_name_js(name), timeout_sec=15.0)
            assert isinstance(name_res, dict) and name_res.get("ok") is True, name_res
            assert str(name_res.get("value")) == name, name_res
            assert name_res.get("saveDisabled") is False, (
                f"agent name must unlock Save (saveDisabled={name_res.get('saveDisabled')})"
            )

            # T2: capabilities tab + bounds on the Max Iterations input.
            probe = wait_for_state(
                client,
                page,
                _CAPABILITIES_INPUT_JS,
                timeout_sec=_warm_ui_parallel_wait_sec(60.0),
            )
            assert probe.get("ready") is True, json.dumps(probe, indent=2, ensure_ascii=False)
            assert probe.get("min") == "5", f"input min mismatch: {probe}"
            assert probe.get("max") == "500", f"input max mismatch: {probe}"

            # T3: set max_iterations then save.
            set_res = client.evaluate(page, _set_max_iterations_js(50), timeout_sec=15.0)
            assert isinstance(set_res, dict) and set_res.get("ok") is True, set_res
            assert str(set_res.get("value")) == "50", set_res
            assert set_res.get("saveDisabled") is False, (
                f"React state must update so the Save button unlocks (saveDisabled={set_res.get('saveDisabled')})"
            )

            client.evaluate(page, _INSTALL_FETCH_TAP_JS, timeout_sec=15.0)
            clicked = wait_for_state(
                client,
                page,
                _click_save_js(),
                timeout_sec=_warm_ui_parallel_wait_sec(20.0),
            )
            assert isinstance(clicked, dict) and clicked.get("ready") is True, clicked

            # T4: creation navigated to ?agentId= and the editor re-rendered the
            # persisted value from the backend.
            done = wait_for_state(
                client,
                page,
                _CREATION_COMPLETE_JS,
                timeout_sec=_warm_ui_parallel_wait_sec(45.0),
            )
            assert done.get("ready") is True, json.dumps(done, indent=2, ensure_ascii=False)
            assert done.get("value") == "50", f"editor re-render mismatch: {done}"

            diag = client.evaluate(
                page,
                """(() => ({
  postBodies: window.__diag_post_bodies__ ?? [],
  url: location.href,
}))()""",
                timeout_sec=15.0,
            )

        agent_id = done["agentId"]
        assert re.fullmatch(r"[0-9a-zA-Z_-]+", agent_id), agent_id

        # T4b: the created agent is queryable and the value persisted.
        _wait_max_iterations(
            api_url,
            agent_id,
            expected=50,
            timeout_sec=30.0,
            diag=json.dumps(diag, ensure_ascii=False),
        )
    finally:
        # The agent is only known after a successful creation; clear it lazily.
        if agent_id := locals().get("agent_id"):
            http_json("DELETE", f"{api_url}/api/v1/user-agents/{agent_id}")
