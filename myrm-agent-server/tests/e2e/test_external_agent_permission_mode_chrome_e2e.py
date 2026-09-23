"""Real Chrome MCP E2E for the external agent permission-mode control.

Asserts the permission-mode selector only offers modes the backend can honour. Both
external-agent types are exercised, because each type resolves its own option set from
`PERMISSION_MODE_OPTIONS`; checking only the default type would silently miss a
regression in the other one.
"""

from __future__ import annotations

import pytest

from tests.support.chrome_mcp_e2e import (
    open_settings_subroute,
    wait_for_state,
)

_DEVELOPER_SECTION_READY_JS = """(() => ({
  ready:
    !!document.querySelector('[data-testid="app-layout"]') &&
    Array.from(document.querySelectorAll('button')).some((btn) =>
      /^\\s*(Add Agent|添加 Agent)\\s*$/i.test(btn.textContent || ''),
    ),
  url: location.href,
}))()"""

_OPEN_AGENT_EDITOR_JS = """(() => {
  const addBtn = Array.from(document.querySelectorAll('button')).find((btn) =>
    /^\\s*(Add Agent|添加 Agent)\\s*$/i.test(btn.textContent || ''),
  );
  if (!addBtn) {
    return { clicked: false, reason: 'missing-add-button' };
  }
  addBtn.click();
  return { clicked: true };
})()"""

_EDITOR_READY_JS = """(() => ({
  ready: !!document.querySelector('[data-testid="external-agent-permission-mode"]'),
}))()"""

_OPEN_PERMISSION_SELECT_JS = """(() => {
  const field = document.querySelector('[data-testid="external-agent-permission-mode"]');
  if (!field) {
    return { ok: false, reason: 'missing-field' };
  }
  const trigger = field.querySelector('button[role="combobox"], button');
  if (!trigger) {
    return { ok: false, reason: 'missing-trigger' };
  }
  trigger.click();
  return { ok: true };
})()"""

# Scoped to the permission options' own testids so an open type dropdown (whose options
# are also role=option) can never leak into the result.
_PERMISSION_OPTIONS_READY_JS = """(() => ({
  ready: document.querySelectorAll('[data-testid^="permission-option-"]').length > 0,
}))()"""

_READ_PERMISSION_OPTIONS_JS = """(() => {
  const options = Array.from(document.querySelectorAll('[data-testid^="permission-option-"]'));
  return {
    ids: options.map((el) => (el.getAttribute('data-testid') || '').replace('permission-option-', '')),
    labels: options.map((el) => (el.textContent || '').trim()),
  };
})()"""

_SELECT_TYPE_JS_TEMPLATE = """(() => {
  const field = document.querySelector('[data-testid="external-agent-type"]');
  if (!field) {
    return { ok: false, reason: 'missing-type-field' };
  }
  const trigger = field.querySelector('button[role="combobox"], button');
  if (!trigger) {
    return { ok: false, reason: 'missing-type-trigger' };
  }
  trigger.click();
  return { ok: true };
})()"""

_CLICK_TYPE_OPTION_JS_TEMPLATE = """(() => {
  const option = document.querySelector('[data-testid="external-agent-type-__TYPE__"]');
  if (!option) {
    return { ok: false, reason: 'missing-type-option' };
  }
  option.click();
  return { ok: true };
})()"""

_TYPE_APPLIED_JS_TEMPLATE = """(() => {
  const field = document.querySelector('[data-testid="external-agent-type"]');
  if (!field) {
    return { ready: false };
  }
  const text = (field.textContent || '').toLowerCase();
  const wanted = '__TYPE__';
  // The trigger reflects the selected value; confirm the switch actually landed before
  // reading the permission options it is supposed to drive.
  const isAcp = /acp|桥接|bridge/.test(text);
  return { ready: wanted === 'acp' ? isAcp : !isAcp };
})()"""


def _permission_option_ids(client: object, page: object) -> list[str]:
    """Open the permission dropdown for the current type and return its option ids."""
    opened = client.evaluate(page, _OPEN_PERMISSION_SELECT_JS, timeout_sec=15.0)
    assert isinstance(opened, dict) and opened.get("ok") is True, f"permission selector not usable: {opened}"

    wait_for_state(client, page, _PERMISSION_OPTIONS_READY_JS, timeout_sec=20.0)
    captured = client.evaluate(page, _READ_PERMISSION_OPTIONS_JS, timeout_sec=10.0)
    assert isinstance(captured, dict)
    return [str(option) for option in captured.get("ids", [])]


def _switch_type(client: object, page: object, agent_type: str) -> None:
    """Switch the external-agent type via its own selector."""
    opened = client.evaluate(page, _SELECT_TYPE_JS_TEMPLATE, timeout_sec=15.0)
    assert isinstance(opened, dict) and opened.get("ok") is True, f"type selector not usable: {opened}"

    click_js = _CLICK_TYPE_OPTION_JS_TEMPLATE.replace("__TYPE__", agent_type)
    clicked = client.evaluate(page, click_js, timeout_sec=15.0)
    assert isinstance(clicked, dict) and clicked.get("ok") is True, f"could not select type {agent_type}: {clicked}"

    applied_js = _TYPE_APPLIED_JS_TEMPLATE.replace("__TYPE__", agent_type)
    wait_for_state(client, page, applied_js, timeout_sec=20.0)


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.integration
def test_external_agent_permission_modes_offer_only_supported_options() -> None:
    """Every external-agent type must offer exactly the modes its runtime can honour."""
    with open_settings_subroute("/settings/developer", timeout_ms=120_000) as (client, page):
        wait_for_state(client, page, _DEVELOPER_SECTION_READY_JS, timeout_sec=90.0)

        opened = client.evaluate(page, _OPEN_AGENT_EDITOR_JS, timeout_sec=15.0)
        assert isinstance(opened, dict)
        assert opened.get("clicked") is True, f"could not open agent editor: {opened}"

        wait_for_state(client, page, _EDITOR_READY_JS, timeout_sec=45.0)

        for agent_type in ("cli", "acp"):
            _switch_type(client, page, agent_type)
            # Assert on stable enum values, not translated copy, so the check cannot rot
            # when labels are reworded or a new locale is added.
            ids = _permission_option_ids(client, page)
            assert sorted(ids) == ["allow_all", "safe"], (
                f"type={agent_type} must offer exactly allow_all+safe, got {ids}"
            )
