"""Real Chrome MCP E2E for the external agent permission-mode control.

Asserts the permission-mode selector only offers modes the backend can honour: CLI and
ACP both expose Full Autonomy and Read-only, and neither advertises an interactive
approval mode that the runtime cannot deliver.
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

_PERMISSION_OPTIONS_JS = """(() => {
  const field = document.querySelector('[data-testid="external-agent-permission-mode"]');
  if (!field) {
    return { ok: false, reason: 'missing-field' };
  }
  const trigger = field.querySelector('button[role="combobox"], button');
  if (!trigger) {
    return { ok: false, reason: 'missing-trigger' };
  }
  trigger.click();
  return { ok: true, opened: true };
})()"""

_READ_OPTIONS_JS = """(() => {
  const ids = Array.from(document.querySelectorAll('[role="option"]'))
    .map((el) => {
      const testId = el.getAttribute('data-testid') || '';
      const option = el.querySelector('[data-testid^="permission-option-"]');
      return (option?.getAttribute('data-testid') || testId).replace('permission-option-', '');
    })
    .filter((id) => id && !id.startsWith('permission-option'));
  const labels = Array.from(document.querySelectorAll('[role="option"]')).map((el) =>
    (el.textContent || '').trim(),
  );
  return { ids, labels };
})()"""


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.integration
def test_external_agent_permission_modes_offer_only_supported_options() -> None:
    """The permission selector must not advertise a mode the runtime cannot honour."""
    with open_settings_subroute("/settings/developer", timeout_ms=120_000) as (client, page):
        wait_for_state(client, page, _DEVELOPER_SECTION_READY_JS, timeout_sec=90.0)

        opened = client.evaluate(page, _OPEN_AGENT_EDITOR_JS, timeout_sec=15.0)
        assert isinstance(opened, dict)
        assert opened.get("clicked") is True, f"could not open agent editor: {opened}"

        wait_for_state(client, page, _EDITOR_READY_JS, timeout_sec=45.0)

        opened_select = client.evaluate(page, _PERMISSION_OPTIONS_JS, timeout_sec=15.0)
        assert isinstance(opened_select, dict)
        assert opened_select.get("ok") is True, f"permission selector not usable: {opened_select}"

        options = wait_for_state(
            client,
            page,
            """(() => {
              const items = Array.from(document.querySelectorAll('[role="option"]'));
              return { ready: items.length > 0, count: items.length };
            })()""",
            timeout_sec=20.0,
        )
        assert options.get("ready") is True, f"permission options did not render: {options}"

        captured = client.evaluate(page, _READ_OPTIONS_JS, timeout_sec=10.0)
        assert isinstance(captured, dict)
        # Assert on stable enum values, not translated copy, so the check cannot rot when
        # labels are reworded or a new locale is added.
        ids = [str(option) for option in captured.get("ids", [])]
        assert sorted(ids) == ["allow_all", "safe"], f"CLI/ACP must offer exactly allow_all+safe, got {ids}"
