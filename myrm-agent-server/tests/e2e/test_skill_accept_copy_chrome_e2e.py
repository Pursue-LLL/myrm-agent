"""Chrome MCP E2E: the skill-confirmation copy a reader actually sees.

The upstream-update confirmation is the only place a reader learns that accepting an
update is reversible: the undo control it points at lives on the skill detail page. The
fixture leaves a prebuilt skill the reader modified while its bundled source moved on,
which is the state that puts "apply upstream update" on screen. This test drives that
control for real, reads the confirmation body from the rendered page, and checks that
the wording promises an undo the page really offers.
"""

from __future__ import annotations

import json

import pytest

from tests.support.chrome_mcp_e2e import (
    _warm_ui_parallel_wait_sec,
    get_e2e_api_url,
    http_json,
    open_settings_subroute,
    prepare_e2e_ui_session,
    wait_for_state,
    warm_ui_route,
)

_SKILL_SEARCH = "systematic-debugging"
_SKILLS_URL = f"/settings/skills?search={_SKILL_SEARCH}"

_SETTINGS_SHELL_STATE = """(() => {
  const bodyText = document.body.innerText || '';
  return {
    ready:
      location.pathname.startsWith('/settings') &&
      bodyText.length > 20 &&
      !!document.querySelector('[data-testid="settings-layout"]'),
    pathname: location.pathname,
    bodyLength: bodyText.length,
  };
})()"""

_SKILL_ROW_STATE = """(() => {
  const panel = document.querySelector('[data-section][data-active="true"]') || document.body;
  const text = panel.innerText || '';
  return {
    ready: /systematic-debugging|Systematic Debugging/i.test(text),
    hasText: text.length > 0,
    sample: text.slice(0, 300),
  };
})()"""

# The skills panel mounts after the settings shell; only then do its tabs exist.
_SKILLS_PANEL_STATE = """(() => {
  const tabs = Array.from(document.querySelectorAll('[role="tab"]')).filter((t) => t.offsetParent !== null);
  return {
    ready: tabs.length > 0,
    tabCount: tabs.length,
    labels: tabs.map((t) => (t.innerText || '').trim()).filter(Boolean).slice(0, 8),
  };
})()"""

ACCEPT_BUTTON_JS = """(() => {
  const labels = %s;
  const visible = (el) => {
    let node = el;
    while (node) {
      if (node.hidden || node.getAttribute('aria-hidden') === 'true') return false;
      if (node instanceof Element) {
        const style = getComputedStyle(node);
        if (style.display === 'none' || style.visibility === 'hidden') return false;
      }
      node = node.parentElement;
    }
    return true;
  };
  const buttons = Array.from(document.querySelectorAll('button')).filter(visible);
  const hit = buttons.find((b) => labels.some((label) => (b.innerText || '').includes(label)));
  if (!hit) {
    return { ok: false, seen: buttons.map((b) => (b.innerText || '').trim()).filter(Boolean).slice(0, 40) };
  }
  hit.click();
  return { ok: true, label: (hit.innerText || '').trim() };
})()"""

_OPEN_SKILL_CARD_JS = """(() => {
  const visible = (el) => {
    let node = el;
    while (node) {
      if (node.hidden || node.getAttribute('aria-hidden') === 'true') return false;
      if (node instanceof Element) {
        const style = getComputedStyle(node);
        if (style.display === 'none' || style.visibility === 'hidden') return false;
      }
      node = node.parentElement;
    }
    return true;
  };
  const cards = Array.from(document.querySelectorAll('[role="presentation"]')).filter(
    (el) => visible(el) && /systematic-debugging|Systematic Debugging/i.test(el.innerText || ''),
  );
  if (cards.length === 0) {
    return { ok: false, count: 0 };
  }
  cards[0].click();
  return { ok: true, count: cards.length };
})()"""

# Reads the open dialog's description verbatim: that is what the reader reads before confirming.
DIALOG_TEXT_JS = """(() => {
  const dialog = document.querySelector('[role="alertdialog"], [role="dialog"]');
  if (!dialog) {
    return { ready: false };
  }
  const text = (dialog.innerText || '').trim();
  return { ready: text.length > 0, text };
})()"""


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="GLOBAL_WRITE",
    workload="STANDARD",
    private_reason="global_write_non_namespace",
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_chrome_ui_upstream_update_confirmation_promises_the_undo_it_offers() -> None:
    """The confirmation the reader opens promises an undo, and the page renders that undo."""
    api_url = get_e2e_api_url()
    seed = http_json("POST", f"{api_url}/api/v1/skills/test/seed-upstream-update-pending")
    assert seed.get("has_upstream_update") is True, json.dumps(seed, indent=2, ensure_ascii=False)
    skill_name = str(seed["skill_name"])

    prepare_e2e_ui_session(api_url)
    # The settings shell pulls a heavy bundle; warming the parent route first keeps the nested
    # navigate from landing on whichever tab the shell restored last.
    warm_ui_route("/settings")
    warm_ui_route(_SKILLS_URL, timeout_sec=_warm_ui_parallel_wait_sec(180.0))

    with open_settings_subroute(_SKILLS_URL, timeout_ms=120_000) as (client, page):
        shell = wait_for_state(
            client,
            page,
            _SETTINGS_SHELL_STATE,
            timeout_sec=_warm_ui_parallel_wait_sec(120.0),
        )
        assert shell.get("ready") is True, json.dumps(shell, indent=2, ensure_ascii=False)

        panel = wait_for_state(
            client, page, _SKILLS_PANEL_STATE, timeout_sec=_warm_ui_parallel_wait_sec(90.0)
        )
        assert panel.get("ready") is True, json.dumps(panel, indent=2, ensure_ascii=False)
        print("E2E_SKILLS_PANEL:", json.dumps(panel, ensure_ascii=False), flush=True)

        row = wait_for_state(client, page, _SKILL_ROW_STATE, timeout_sec=_warm_ui_parallel_wait_sec(90.0))
        assert row.get("ready") is True, json.dumps(row, indent=2, ensure_ascii=False)

        # The apply control lives in the skill's detail sheet, so the card is opened first.
        card = client.evaluate(page, _OPEN_SKILL_CARD_JS, timeout_sec=20.0)
        assert isinstance(card, dict) and card.get("ok") is True, json.dumps(card, ensure_ascii=False)[:600]

        opened = client.evaluate(
            page,
            ACCEPT_BUTTON_JS % json.dumps(["Apply Update", "应用更新", "Upstream-Update anwenden", "업데이트 적용"]),
            timeout_sec=20.0,
        )
        assert isinstance(opened, dict) and opened.get("ok") is True, json.dumps(opened, ensure_ascii=False)[:800]

        dialog = wait_for_state(client, page, DIALOG_TEXT_JS, timeout_sec=30.0)
        assert dialog.get("ready") is True, json.dumps(dialog, indent=2, ensure_ascii=False)
        text = str(dialog.get("text") or "")
        assert skill_name in text, f"the confirmation does not name the skill it edits: {text!r}"

        # A translation that still reads "cannot be undone" contradicts the undo the detail page
        # renders for the very update being confirmed.
        lowered = text.lower()
        asserts_irreversible = any(
            marker in lowered
            for marker in ("cannot be undone", "nicht rückgängig", "取り消せません", "되돌릴 수 없습니다", "不可撤销", "不可撤銷")
        )
        assert not asserts_irreversible, f"confirmation still claims the update is permanent: {text!r}"
        assert "undo" in lowered or "rückgängig" in lowered or "되돌릴" in lowered or "撤銷" in lowered or "撤销" in lowered, (
            f"confirmation does not promise the undo the page offers: {text!r}"
        )
