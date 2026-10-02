"""Chrome MCP E2E: x-live-search prebuilt skill card on /settings/skills.

Real user flow: open Settings → Skills, switch to the Installed tab, and verify
the x-live-search prebuilt skill card renders with a state consistent with the
live /api/v1/skills/available registry (version 1.1.0, and the credential-gated
unavailable hint when no xAI provider key is configured).

Environment-adaptive assertion: the card's availability hint must always match
the live API state, regardless of whether an xAI key happens to be configured.
"""

from __future__ import annotations

import json

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

_SKILL_ID = "x-live-search"

# Card-level probe: ensure the Installed tab is active (idempotent pointer
# dispatch each poll — Radix switches on mousedown, and the tab may render
# after the first evaluate), then look for the x-live-search card block.
_SKILL_CARD_JS = """(() => {
  const tabs = Array.from(document.querySelectorAll('[role="tab"]'));
  const installed = tabs.find((t) => /^(Installed|已安装|已安裝)(\\d*)$/.test((t.textContent || '').trim()));
  if (installed && installed.getAttribute('aria-selected') !== 'true') {
    const opts = {
      bubbles: true,
      cancelable: true,
      composed: true,
      button: 0,
      ctrlKey: false,
      detail: 1,
      view: window,
    };
    installed.dispatchEvent(new PointerEvent('pointerdown', { ...opts, pointerId: 1, isPrimary: true }));
    installed.dispatchEvent(new MouseEvent('mousedown', opts));
    installed.dispatchEvent(new PointerEvent('pointerup', { ...opts, pointerId: 1, isPrimary: true }));
    installed.dispatchEvent(new MouseEvent('mouseup', opts));
    installed.dispatchEvent(new MouseEvent('click', opts));
  }
  const text = document.body?.innerText || '';
  const hasSkill = text.includes('x-live-search');
  const hasXaiHint = /Add an xAI provider|添加 xAI/i.test(text);
  return {
    ready: hasSkill,
    tabFound: !!installed,
    tabSelected: installed ? installed.getAttribute('aria-selected') === 'true' : false,
    hasSkill,
    hasXaiHint,
    snippet: text.slice(0, 400),
  };
})()"""


def _fetch_registry_entry() -> dict[str, object]:
    """Read the live skill registry entry for x-live-search over the real API."""
    resp = http_json("GET", f"{get_e2e_api_url()}/api/v1/skills/available")
    assert isinstance(resp, dict), f"Expected dict, got {type(resp)}"
    entries = resp.get("skills")
    assert isinstance(entries, list), f"Expected skills list, got {type(entries)}"
    return next((s for s in entries if s.get("id") == _SKILL_ID), {})


def _ensure_skill_enabled() -> None:
    """Enable x-live-search like a real user would before checking the card."""
    entry = _fetch_registry_entry()
    if entry:
        return
    enabled = http_json("POST", f"{get_e2e_api_url()}/api/v1/skills/{_SKILL_ID}/enable")
    assert isinstance(enabled, dict), f"Expected dict, got {type(enabled)}"
    assert enabled.get("enabled") is True, json.dumps(enabled, ensure_ascii=False)
    entry = _fetch_registry_entry()
    assert entry, f"{_SKILL_ID} missing from /api/v1/skills/available after enable"


# PRIVATE+exclusive_backend: workspace harness often drifts from shared :8080;
# SHARED would epoch-skip under PRIVATE_EPOCH_REQUIRED (TAB-9 requires private_reason).
@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="GLOBAL_WRITE",
    workload="STANDARD",
    private_reason="global_write_non_namespace",
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_chrome_ui_x_live_search_skill_card_matches_registry() -> None:
    """x-live-search card state must render consistently with the live registry."""
    api_url = get_e2e_api_url()
    prepare_e2e_ui_session(api_url)

    # Live registry contract first: the skill is active, at version 1.1.0.
    _ensure_skill_enabled()
    entry = _fetch_registry_entry()
    assert entry, f"{_SKILL_ID} missing from registry after enable"
    assert entry.get("is_active") is True, json.dumps(entry, ensure_ascii=False)
    assert entry.get("version") == "1.1.0", json.dumps(entry, ensure_ascii=False)
    registry_available = bool(entry.get("available"))
    unavailable_reason = str(entry.get("unavailable_reason") or "")

    # Skills tab pulls a heavy bundle — warm parent route first (settings E2E pattern).
    warm_ui_route("/settings")
    warm_ui_route(
        "/settings/skills",
        timeout_sec=_warm_ui_parallel_wait_sec(180.0),
    )
    with open_settings_subroute(
        "/settings/skills",
        timeout_ms=120_000,
    ) as (client, page):
        dismiss_blocking_modals(client, page)

        state = wait_for_state(
            client,
            page,
            _SKILL_CARD_JS,
            timeout_sec=_warm_ui_parallel_wait_sec(90.0),
        )
        assert state.get("ready") is True, json.dumps(state, indent=2, ensure_ascii=False)
        assert state.get("tabFound") is True, json.dumps(state, indent=2, ensure_ascii=False)
        assert state.get("tabSelected") is True, json.dumps(state, indent=2, ensure_ascii=False)
        assert state.get("hasSkill") is True

        # Environment-adaptive consistency: the credential-gated hint on the card
        # must match the live registry availability state.
        if not registry_available:
            assert unavailable_reason, json.dumps(entry, ensure_ascii=False)
            assert state.get("hasXaiHint") is True, json.dumps(state, indent=2, ensure_ascii=False)
        else:
            # With a configured xAI provider the card must drop the hint.
            assert state.get("hasXaiHint") is False, json.dumps(state, indent=2, ensure_ascii=False)
