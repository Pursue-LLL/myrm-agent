"""Chrome E2E (SHARED): Connect Wizard renders wiki tools in the plugin SKILL.md.

Walks the real user flow in the browser on /settings/memory:

1. Create a real agent via the public API with ``enabled_builtin_tools=["wiki"]``
   (the exact field the /mcp wiki gate and the SKILL renderer both read).
2. Switch to the Verify section and open the Connect Wizard.
3. Pick the wiki-enabled agent in the agent Select (radix combobox).
4. Generate the Agent Plugins bundle and wait for the plugin step.
5. Switch the file Select to ``skills/myrm-memory/SKILL.md`` and assert the
   rendered markdown contains the wiki tool contract (``wiki_query``,
   ``wiki_ingest``, ``wiki_apply`` and the wiki section heading).

Zero drift proof: the same agent flag drives the MCP tool list and the SKILL
contract, so a browser-visible SKILL.md with the wiki section means the bundle
never describes tools the endpoint would hide.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import pytest

from tests.support.chrome_mcp_e2e import (
    ChromeMcpClient,
    McpPage,
    dismiss_blocking_modals,
    get_e2e_api_url,
    http_json,
    open_settings_subroute,
    prepare_e2e_ui_session,
    wait_for_state,
    warm_ui_route,
)

_AGENT_NAME = "agent-wiki-e2e"
_SKILL_FILE = "skills/myrm-memory/SKILL.md"

# Radix Select interactions need pointer events (not a bare click) to pick an
# option, and the trigger toggles on click. All selects are scoped to the open
# wizard dialog so page-level comboboxes can never be mistaken for it.
_OPEN_CONNECT_WIZARD_JS = """(() => {
  const findBtn = (re) => Array.from(document.querySelectorAll('button')).find(
    (el) => re.test((el.textContent || '').trim()),
  );
  const verifyBtn = findBtn(/^(Verify|验证)$/);
  if (!verifyBtn) {
    return { ready: false, clicked: false, why: 'no Verify/验证 section button',
             text: (document.body?.textContent || '').slice(0, 700) };
  }
  verifyBtn.click();
  const connectBtn = findBtn(/^Connect$/);
  if (!connectBtn) {
    return { ready: false, clicked: false, why: 'no Connect button',
             text: (document.body?.textContent || '').slice(0, 700) };
  }
  connectBtn.click();
  return { ready: true, clicked: true };
})()"""

_OPEN_AGENT_SELECT_JS = """(() => {
  const dlg = document.querySelector('[role="dialog"]');
  const trigger = dlg ? dlg.querySelector('button[role="combobox"]') : null;
  if (!trigger) {
    return { ready: false, why: 'no combobox inside wizard dialog',
             text: (document.body?.textContent || '').slice(0, 700) };
  }
  trigger.click();
  return { ready: true, clicked: true };
})()"""

_PICK_AGENT_OPTION_JS = """(() => {
  const listbox = document.querySelector('[role="listbox"]');
  if (!listbox) return { ready: false, why: 'no listbox open' };
  const option = Array.from(listbox.querySelectorAll('[role="option"]')).find(
    (el) => (el.textContent || '').includes('""" + _AGENT_NAME + """'),
  );
  if (!option) {
    return { ready: false, why: 'agent option not rendered yet',
             options: Array.from(listbox.querySelectorAll('[role="option"]')).map((el) => (el.textContent || '').trim()) };
  }
  const opts = { bubbles: true, cancelable: true, view: window, pointerId: 1 };
  option.dispatchEvent(new PointerEvent('pointerdown', opts));
  option.dispatchEvent(new PointerEvent('pointerup', opts));
  option.dispatchEvent(new MouseEvent('mouseup', opts));
  option.click();
  return { ready: true, clicked: true };
})()"""

_AGENT_SELECTED_JS = """(() => {
  const dlg = document.querySelector('[role="dialog"]');
  const trigger = dlg ? dlg.querySelector('button[role="combobox"]') : null;
  const text = (trigger?.textContent || '');
  return { ready: text.includes('""" + _AGENT_NAME + """'), triggerText: text.trim() };
})()"""

_DIALOG_GENERATE_BTN_READY_JS = """(() => {
  const text = document.body?.textContent || '';
  const btn = Array.from(document.querySelectorAll('button')).find(
    (el) => /Generate Agent Plugins bundle|生成 Agent Plugins 插件/.test(el.textContent || ''),
  );
  return { ready: !!btn, hasBtn: !!btn, text: text.slice(0, 800) };
})()"""

_CLICK_GENERATE_BUNDLE_JS = """(() => {
  const btn = Array.from(document.querySelectorAll('button')).find(
    (el) => /Generate Agent Plugins bundle|生成 Agent Plugins 插件/.test(el.textContent || ''),
  );
  if (!btn || btn.disabled) return { ready: false, clicked: false, disabled: btn?.disabled ?? null };
  btn.click();
  return { ready: true, clicked: true };
})()"""

_PLUGIN_STEP_READY_JS = """(() => {
  const text = document.body?.textContent || '';
  const ready = /Agent Plugins bundle ready|Agent Plugins 插件/.test(text) &&
    Array.from(document.querySelectorAll('button')).some(
      (el) => /Download All \\(.zip\\)|下载全部 \\(.zip\\)/.test(el.textContent || ''),
    );
  return { ready, text: text.slice(0, 1200) };
})()"""

_OPEN_FILE_SELECT_JS = """(() => {
  const dlg = document.querySelector('[role="dialog"]');
  const comboboxes = dlg ? Array.from(dlg.querySelectorAll('button[role="combobox"]')) : [];
  if (comboboxes.length === 0) {
    return { ready: false, why: 'no file combobox rendered', text: (document.body?.textContent || '').slice(0, 700) };
  }
  comboboxes[0].click();
  return { ready: true, clicked: true };
})()"""

_PICK_SKILL_OPTION_JS = """(() => {
  const listbox = document.querySelector('[role="listbox"]');
  if (!listbox) return { ready: false, why: 'no file listbox open' };
  const option = Array.from(listbox.querySelectorAll('[role="option"]')).find(
    (el) => (el.textContent || '').trim() === '""" + _SKILL_FILE + """',
  );
  if (!option) {
    return { ready: false, why: 'skill file option not rendered yet',
             options: Array.from(listbox.querySelectorAll('[role="option"]')).map((el) => (el.textContent || '').trim()) };
  }
  const opts = { bubbles: true, cancelable: true, view: window, pointerId: 1 };
  option.dispatchEvent(new PointerEvent('pointerdown', opts));
  option.dispatchEvent(new PointerEvent('pointerup', opts));
  option.dispatchEvent(new MouseEvent('mouseup', opts));
  option.click();
  return { ready: true, clicked: true };
})()"""

_SKILL_CONTENT_STATE_JS = """(() => {
  const dlg = document.querySelector('[role="dialog"]');
  const pre = dlg ? dlg.querySelector('pre') : null;
  const text = pre ? (pre.textContent || '') : '';
  return {
    ready: pre !== null && text.includes('wiki_query') &&
      text.includes('wiki_ingest') && text.includes('wiki_apply') &&
      text.includes('Search the compiled knowledge base first'),
    hasPre: pre !== null,
    length: text.length,
    head: text.slice(0, 300),
  };
})()"""


def _create_wiki_agent() -> str:
    """Create the wiki-enabled agent via the public API; return its real id."""
    payload = http_json(
        "POST",
        f"{get_e2e_api_url().rstrip('/')}/api/v1/user-agents",
        {"name": _AGENT_NAME, "description": "pytest chrome e2e wiki agent", "enabled_builtin_tools": ["wiki"]},
    )
    data = payload.get("data") if isinstance(payload, dict) else None
    agent_id = data.get("id") if isinstance(data, dict) else None
    if not isinstance(agent_id, str) or not agent_id:
        raise RuntimeError(f"agent create response missing data.id: {payload!r}")
    return agent_id


def _delete_wiki_agent(agent_id: str) -> None:
    http_json(
        "DELETE",
        f"{get_e2e_api_url().rstrip('/')}/api/v1/user-agents/{agent_id}",
        expected_statuses=frozenset({200, 204}),
    )


@contextmanager
def _connect_wizard_open() -> Iterator[tuple[ChromeMcpClient, McpPage]]:
    prepare_e2e_ui_session(get_e2e_api_url())
    warm_ui_route("/settings/memory")
    with open_settings_subroute("/settings/memory", timeout_ms=120_000) as (client, page):
        dismiss_blocking_modals(client, page)
        opened = wait_for_state(client, page, _OPEN_CONNECT_WIZARD_JS, timeout_sec=90.0)
        print(f"[connect-wizard-wiki-e2e] opened={opened}", flush=True)
        assert opened.get("clicked") is True, opened
        dialog = wait_for_state(client, page, _DIALOG_GENERATE_BTN_READY_JS, timeout_sec=60.0)
        print(f"[connect-wizard-wiki-e2e] dialog={dialog}", flush=True)
        assert dialog.get("ready") is True, dialog
        yield client, page


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_connect_wizard_wiki_agent_skill_bundle_chrome_e2e() -> None:
    """Real user flow: wiki-enabled agent's plugin bundle SKILL.md shows wiki tools."""
    agent_id = _create_wiki_agent()
    try:
        with _connect_wizard_open() as (client, page):
            # Pick the wiki-enabled agent in the wizard's agent Select.
            opened = wait_for_state(client, page, _OPEN_AGENT_SELECT_JS, timeout_sec=30.0)
            assert opened.get("ready") is True, opened
            picked = wait_for_state(client, page, _PICK_AGENT_OPTION_JS, timeout_sec=30.0)
            assert picked.get("ready") is True, picked
            selected = wait_for_state(client, page, _AGENT_SELECTED_JS, timeout_sec=30.0)
            assert selected.get("ready") is True, selected
            print(f"[connect-wizard-wiki-e2e] agent selected: {selected.get('triggerText')}", flush=True)

            # Generate the bundle; the plugin step renders the file viewer.
            generated = wait_for_state(client, page, _CLICK_GENERATE_BUNDLE_JS, timeout_sec=30.0)
            assert generated.get("clicked") is True, generated
            plugin_step = wait_for_state(client, page, _PLUGIN_STEP_READY_JS, timeout_sec=90.0)
            assert plugin_step.get("ready") is True, plugin_step

            # Switch the file viewer to the SKILL.md contract.
            file_open = wait_for_state(client, page, _OPEN_FILE_SELECT_JS, timeout_sec=30.0)
            assert file_open.get("ready") is True, file_open
            skill_picked = wait_for_state(client, page, _PICK_SKILL_OPTION_JS, timeout_sec=30.0)
            assert skill_picked.get("ready") is True, skill_picked

            content = wait_for_state(client, page, _SKILL_CONTENT_STATE_JS, timeout_sec=30.0)
            print(f"[connect-wizard-wiki-e2e] skill content: {content}", flush=True)
            assert content.get("ready") is True, content
            assert content.get("hasPre") is True, content
            assert content.get("length", 0) > 0, content
    finally:
        _delete_wiki_agent(agent_id)


__all__ = ["test_connect_wizard_wiki_agent_skill_bundle_chrome_e2e"]
