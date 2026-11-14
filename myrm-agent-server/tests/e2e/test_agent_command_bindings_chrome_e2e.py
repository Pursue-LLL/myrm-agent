"""Chrome E2E: slash-command bindings are edited in Settings > Agents and persist.

Prerequisites:
  ./myrm-dev ready --attach --chrome

Covers the command-bindings card in the agent editor's Capabilities tab, end to end through the real UI and API:
  T1 - Add: a new binding (command name + skill) is saved by the panel's single Save button and reaches the backend.
  T2 - Remove: deleting the only binding and saving clears the bindings stored for the agent.
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Callable

import pytest

from tests.support.chrome_mcp_e2e import (
    ChromeMcpClient,
    McpPage,
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
    localStorage.setItem('myrm.proactive.dismissed.migration-discovery', 'forever');
  } catch (err) {
    return { ok: false, err: String(err) };
  }
  return { ok: true };
})()"""

# Opens the Capabilities tab and reports the bindings card once its editor is interactive.
_BINDINGS_CARD_JS = """(() => {
  const tab = document.querySelector('[data-testid="agent-tab-capabilities"]');
  if (!tab) {
    return { ready: false, reason: 'no-capabilities-tab' };
  }
  tab.click();
  const card = document.querySelector('[data-testid="agent-command-bindings"]');
  const add = card ? card.querySelector('[data-testid="command-binding-add"]') : null;
  const rows = card ? Array.from(card.querySelectorAll('[data-testid="command-binding-row"]')) : [];
  return {
    ready: !!add,
    hasCard: !!card,
    rowCount: rows.length,
    rowTexts: rows.map((row) => (row.textContent || '').trim()),
    bodyLength: (document.body?.innerText || '').length,
  };
})()"""

# Polled until the new row shows its name field; the guard keeps repeated polls from adding more than one row.
_ADD_BINDING_JS = """(() => {
  const card = document.querySelector('[data-testid="agent-command-bindings"]');
  if (!card) {
    return { ready: false, reason: 'no-card' };
  }
  if (!window.__e2eBindingAdded) {
    const add = card.querySelector('[data-testid="command-binding-add"]');
    if (!add) {
      return { ready: false, reason: 'no-add-button' };
    }
    add.click();
    window.__e2eBindingAdded = true;
  }
  const name = card.querySelector('[data-testid="command-binding-name"]');
  return {
    ready: !!name,
    rowCount: card.querySelectorAll('[data-testid="command-binding-row"]').length,
    bodyLength: (document.body?.innerText || '').length,
  };
})()"""

# Sets the field through the native setter so React's onChange fires.
_FILL_NAME_JS = """(() => {
  const input = document.querySelector('[data-testid="agent-command-bindings"] [data-testid="command-binding-name"]');
  if (!input) {
    return { ready: false, reason: 'no-name-input' };
  }
  const setter = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(input), 'value');
  setter.set.call(input, __COMMAND__);
  input.dispatchEvent(new InputEvent('input', { bubbles: true, data: __COMMAND__ }));
  return new Promise((resolve) => setTimeout(() => resolve({ ready: input.value === __COMMAND__, value: input.value }), 200));
})()"""

_SELECT_SKILL_JS = """(() => {
  const chips = Array.from(
    document.querySelectorAll('[data-testid="agent-command-bindings"] [data-testid="command-binding-skill"]'),
  );
  const chip = chips.find((el) => (el.textContent || '').trim() === __SKILL_NAME__);
  if (!chip) {
    return { ready: false, reason: 'no-skill-chip', chips: chips.map((el) => (el.textContent || '').trim()) };
  }
  if (chip.getAttribute('aria-pressed') !== 'true') {
    chip.click();
  }
  return new Promise((resolve) => setTimeout(() => resolve({ ready: chip.getAttribute('aria-pressed') === 'true' }), 200));
})()"""

_REMOVE_BINDING_JS = """(() => {
  const remove = document.querySelector('[data-testid="agent-command-bindings"] [data-testid="command-binding-remove"]');
  if (!remove) {
    return { ready: false, reason: 'no-remove-button' };
  }
  remove.click();
  return new Promise((resolve) => setTimeout(() => resolve({
    ready: document.querySelectorAll('[data-testid="agent-command-bindings"] [data-testid="command-binding-row"]').length === 0,
  }), 200));
})()"""

# The panel has one Save button for every tab. Scoped to the agents section and to visible buttons, because settings
# keeps visited tabs mounted with `hidden`.
_CLICK_SAVE_JS = """(() => {
  const section = document.querySelector('[data-section="agents"]') || document.body;
  const matches = Array.from(section.querySelectorAll('button')).filter((btn) =>
    /^(Save|保存|儲存)$/i.test((btn.textContent || '').trim()) && btn.offsetParent !== null,
  );
  const save = matches.find((btn) => !btn.disabled);
  const bodyLength = (document.body?.innerText || '').length;
  if (!save) {
    return { ready: false, reason: 'no-enabled-visible-save-button', bodyLength };
  }
  save.click();
  return { ready: true, clicked: (save.textContent || '').trim(), bodyLength };
})()"""

# After a successful save the panel has nothing left to save, so Save is disabled again and its spinner is gone.
_SAVE_COMPLETE_JS = """(() => {
  const section = document.querySelector('[data-section="agents"]') || document.body;
  const save = Array.from(section.querySelectorAll('button')).find((btn) =>
    /^(Save|保存|儲存)$/i.test((btn.textContent || '').trim()) && btn.offsetParent !== null,
  );
  const bodyLength = (document.body?.innerText || '').length;
  if (!save) {
    return { ready: false, reason: 'no-visible-save-button', bodyLength };
  }
  const hasSpinner = !!save.querySelector('.animate-spin');
  return { ready: save.disabled && !hasSpinner, disabled: save.disabled, hasSpinner, bodyLength };
})()"""


def _create_agent(api_url: str, *, name: str) -> str:
    resp = http_json("POST", f"{api_url}/api/v1/user-agents", {"name": name})
    data = resp["data"]
    agent_id = data.get("id") or data.get("agent_id")
    assert isinstance(agent_id, str) and agent_id, json.dumps(data, ensure_ascii=False)
    return agent_id


def _first_skill(api_url: str) -> tuple[str, str]:
    """The (id, name) of the first listed skill: the editor offers exactly these as the binding's targets."""
    resp = http_json("GET", f"{api_url}/api/v1/skills?sort_by=name&order=asc")
    payload = resp.get("data", resp)
    skills = payload.get("skills") if isinstance(payload, dict) else None
    assert isinstance(skills, list) and skills, f"the runtime must list at least one skill: {json.dumps(resp)[:300]}"
    skill = skills[0]
    assert isinstance(skill.get("id"), str) and isinstance(skill.get("name"), str), skill
    return skill["id"], skill["name"]


def _fetch_bindings(api_url: str, agent_id: str) -> list[dict[str, object]] | None:
    resp = http_json("GET", f"{api_url}/api/v1/user-agents/{agent_id}")
    return (resp.get("data") or {}).get("command_bindings")


def _wait_bindings(
    api_url: str,
    agent_id: str,
    accept: Callable[[list[dict[str, object]] | None], bool],
    *,
    timeout_sec: float = 30.0,
) -> list[dict[str, object]] | None:
    """Poll the stored bindings until ``accept`` holds; the last value is returned for the caller's assertion."""
    deadline = time.monotonic() + timeout_sec
    last = _fetch_bindings(api_url, agent_id)
    while not accept(last) and time.monotonic() < deadline:
        time.sleep(1.0)
        last = _fetch_bindings(api_url, agent_id)
    return last


def _open_editor(client: ChromeMcpClient, page: McpPage) -> dict[str, object]:
    """Dismiss overlays and wait for the Capabilities tab to show the bindings card."""
    client.evaluate(page, _DISMISS_MIGRATION_JS, timeout_sec=15.0)
    dismiss_blocking_modals(client, page)
    return wait_for_state(client, page, _BINDINGS_CARD_JS, timeout_sec=_warm_ui_parallel_wait_sec(60.0))


def _save_through_panel(client: ChromeMcpClient, page: McpPage) -> None:
    clicked = wait_for_state(client, page, _CLICK_SAVE_JS, timeout_sec=_warm_ui_parallel_wait_sec(20.0))
    assert clicked.get("ready") is True, clicked
    saved = wait_for_state(client, page, _SAVE_COMPLETE_JS, timeout_sec=_warm_ui_parallel_wait_sec(30.0))
    assert saved.get("ready") is True, json.dumps(saved, indent=2, ensure_ascii=False)


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_command_binding_add_persists_via_ui() -> None:
    """A binding built in the editor is stored for the agent with its command name and chosen skill."""
    api_url = get_e2e_api_url()
    prepare_e2e_ui_session(api_url)
    skill_id, skill_name = _first_skill(api_url)

    agent_id = _create_agent(api_url, name=f"cmd-add-e2e-{uuid.uuid4().hex[:8]}")
    command = f"e2e{uuid.uuid4().hex[:6]}"
    try:
        assert not _fetch_bindings(api_url, agent_id), "a fresh agent must start without slash commands"

        warm_ui_route("/settings")
        with open_settings_subroute(f"/settings/agents?agentId={agent_id}", timeout_ms=120_000) as (client, page):
            card = _open_editor(client, page)
            assert card.get("rowCount") == 0, f"a fresh agent must show an empty bindings card: {card}"

            added = wait_for_state(client, page, _ADD_BINDING_JS, timeout_sec=_warm_ui_parallel_wait_sec(30.0))
            assert added.get("rowCount") == 1, added

            filled = client.evaluate(page, _FILL_NAME_JS.replace("__COMMAND__", json.dumps(command)), timeout_sec=15.0)
            assert isinstance(filled, dict) and filled.get("ready") is True, filled

            picked = wait_for_state(
                client,
                page,
                _SELECT_SKILL_JS.replace("__SKILL_NAME__", json.dumps(skill_name)),
                timeout_sec=_warm_ui_parallel_wait_sec(30.0),
            )
            assert picked.get("ready") is True, picked

            _save_through_panel(client, page)

            shown = client.evaluate(page, _BINDINGS_CARD_JS, timeout_sec=15.0)
            assert isinstance(shown, dict) and shown.get("rowCount") == 1, shown
            row_text = str(shown["rowTexts"][0])
            assert f"/{command}" in row_text and skill_name in row_text, f"the saved row must show its command and skill: {shown}"

        stored = _wait_bindings(api_url, agent_id, lambda bindings: bool(bindings))
        assert stored is not None and len(stored) == 1, f"the backend must store exactly one binding: {stored}"
        assert stored[0].get("command_name") == command, stored
        assert stored[0].get("skill_ids") == [skill_id], stored
    finally:
        http_json("DELETE", f"{api_url}/api/v1/user-agents/{agent_id}")


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_command_binding_remove_persists_via_ui() -> None:
    """Deleting the last binding in the editor clears the bindings stored for the agent."""
    api_url = get_e2e_api_url()
    prepare_e2e_ui_session(api_url)
    skill_id, skill_name = _first_skill(api_url)

    agent_id = _create_agent(api_url, name=f"cmd-rm-e2e-{uuid.uuid4().hex[:8]}")
    command = f"e2e{uuid.uuid4().hex[:6]}"
    try:
        seeded = http_json(
            "PUT",
            f"{api_url}/api/v1/user-agents/{agent_id}",
            {"command_bindings": [{"command_name": command, "skill_ids": [skill_id]}]},
        )
        assert (seeded.get("data") or {}).get("command_bindings"), f"seeding must store the binding: {seeded}"

        warm_ui_route("/settings")
        with open_settings_subroute(f"/settings/agents?agentId={agent_id}", timeout_ms=120_000) as (client, page):
            card = _open_editor(client, page)
            assert card.get("rowCount") == 1, f"the editor must load the stored binding: {card}"
            row_text = str(card["rowTexts"][0])
            assert f"/{command}" in row_text and skill_name in row_text, f"the loaded row must show its command and skill: {card}"

            removed = client.evaluate(page, _REMOVE_BINDING_JS, timeout_sec=15.0)
            assert isinstance(removed, dict) and removed.get("ready") is True, removed

            _save_through_panel(client, page)

        stored = _wait_bindings(api_url, agent_id, lambda bindings: not bindings)
        assert not stored, f"the backend must hold no bindings after the user removed the last one: {stored}"
    finally:
        http_json("DELETE", f"{api_url}/api/v1/user-agents/{agent_id}")
