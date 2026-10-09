"""Real Chrome E2E: keyboard focus on the borderless workspace path input shows a visible focus ring.

[INPUT]
- tests.support.chrome_mcp_e2e (POS: Chrome MCP test framework)
- myrm-agent-frontend NewTaskWorkContextCard (POS: empty-chat work context card with workspace path picker)

[OUTPUT]
- test_workspace_path_input_has_visible_focus_ring_chrome_e2e: focused path input paints a ring and is not clipped

[POS]
- Real-browser guard for the Input focus ring that static class scanning cannot prove.
"""

from __future__ import annotations

import json
import os
import urllib.request
from typing import cast

import pytest
from websockets.sync.client import connect

from tests.support.chrome_mcp_e2e import (
    get_e2e_api_url,
    get_e2e_ui_url,
    open_mcp_page,
    prepare_e2e_ui_session,
    wait_for_state,
    warm_ui_route,
)

_OPEN_PICKER_JS = """(() => {
  const card = document.querySelector('[data-testid="new-task-work-context-card"]');
  if (!card) return { ready: false, reason: 'no-card' };
  const local = card.querySelector('[data-testid="context-mode-local"]');
  if (local) local.click();
  const trigger = card.querySelector('[data-testid="workspace-picker-trigger"]');
  if (!trigger) return { ready: false, reason: 'no-trigger' };
  if (trigger.getAttribute('aria-expanded') !== 'true') trigger.click();
  const input = document.querySelector('[data-radix-popper-content-wrapper] input');
  return { ready: Boolean(input), reason: input ? 'ok' : 'no-input' };
})()"""

# Text inputs always match :focus-visible, so a programmatic focus() reproduces Tab arrival.
_FOCUS_AND_MEASURE_JS = """(() => {
  const input = document.querySelector('[data-radix-popper-content-wrapper] input');
  if (!input) return { ready: false, reason: 'no-input' };
  input.focus();
  const style = getComputedStyle(input);
  const rect = input.getBoundingClientRect();
  const clippedBy = [];
  for (let el = input.parentElement; el; el = el.parentElement) {
    const overflow = getComputedStyle(el).overflow;
    if (overflow === 'visible') continue;
    const box = el.getBoundingClientRect();
    const ringPx = 1;
    if (
      rect.left - ringPx < box.left ||
      rect.right + ringPx > box.right ||
      rect.top - ringPx < box.top ||
      rect.bottom + ringPx > box.bottom
    ) {
      clippedBy.push(el.tagName + '[' + overflow + ']');
    }
  }
  return {
    ready: true,
    focused: document.activeElement === input,
    focusVisible: input.matches(':focus-visible'),
    matchesFocus: input.matches(':focus'),
    docHasFocus: document.hasFocus(),
    className: input.className,
    boxShadow: style.boxShadow.split(/,(?![^(]*\\))/).filter((s) => !s.includes('rgba(0, 0, 0, 0)')).join(','),
    outlineStyle: style.outlineStyle,
    clippedBy,
  };
})()"""


def _evaluate_with_focus_emulation(target_id: str, expression: str) -> dict[str, object]:
    """Evaluate on a CDP session that emulates page focus.

    Parked E2E windows have no OS focus, so :focus-visible only matches while a CDP
    session keeps focus emulation enabled; the override ends with the session.
    """
    port = os.environ.get("MYRM_CHROME_E2E_PORT", "9333")
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=5) as resp:
        ws_url = next(t["webSocketDebuggerUrl"] for t in json.load(resp) if t["id"] == target_id)
    with connect(ws_url, open_timeout=10, close_timeout=5) as ws:
        calls = (
            (1, "Emulation.setFocusEmulationEnabled", {"enabled": True}),
            (2, "Runtime.evaluate", {"expression": expression, "returnByValue": True}),
        )
        reply: dict[str, object] = {}
        for call_id, method, params in calls:
            ws.send(json.dumps({"id": call_id, "method": method, "params": params}))
            while (reply := json.loads(ws.recv(timeout=15))).get("id") != call_id:
                pass
        result = cast("dict[str, dict[str, dict[str, object]]]", reply)["result"]
        return cast("dict[str, object]", result["result"]["value"])


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="STANDARD",
    private_reason="exclusive_backend",
)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_workspace_path_input_has_visible_focus_ring_chrome_e2e() -> None:
    """The borderless workspace path input must paint the shared Input ring when keyboard-focused."""
    prepare_e2e_ui_session(get_e2e_api_url())
    warm_ui_route("/")

    with open_mcp_page(f"{get_e2e_ui_url()}/") as (client, page):
        wait_for_state(client, page, _OPEN_PICKER_JS, timeout_sec=60.0)

        measured = _evaluate_with_focus_emulation(str(page.target_id), _FOCUS_AND_MEASURE_JS)

    detail = json.dumps(measured)
    assert isinstance(measured, dict) and measured.get("ready") is True, detail
    assert measured.get("focused") is True, detail
    assert measured.get("focusVisible") is True, detail
    assert measured.get("boxShadow") not in (None, "", "none"), detail
    assert measured.get("clippedBy") == [], detail
