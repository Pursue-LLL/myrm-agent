"""Real Chrome MCP E2E for ComposerInlineContextChipStrip unified lifecycle and interactions."""

from __future__ import annotations

import json

import pytest

from tests.support.chrome_mcp_e2e import (
    _warm_ui_parallel_wait_sec,
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_mcp_page,
    prepare_e2e_ui_session,
    wait_for_state,
    warm_ui_route,
)

_SKILL_ID = "systematic-debugging"
_SLASH_QUERY = "systematic"


def _ensure_skill_enabled(api_url: str, skill_id: str) -> None:
    try:
        http_json(
            "POST",
            f"{api_url}/api/v1/skills/test/ensure-prebuilt-catalog",
            expected_statuses=frozenset({200, 201, 404}),
        )
    except RuntimeError:
        pass

    config = http_json("GET", f"{api_url}/api/v1/skills/config")
    assert isinstance(config, dict)
    enabled = list(config.get("enabled_prebuilt_ids") or [])
    if skill_id in enabled:
        return
    enabled.append(skill_id)
    http_json(
        "PUT",
        f"{api_url}/api/v1/skills/config",
        {"enabled_prebuilt_ids": enabled},
    )


def _seed_composer_fixture(api_url: str) -> dict[str, object]:
    seeded = http_json(
        "POST",
        f"{api_url}/api/v1/chats/test/seed-skill-chip-composer-fixture",
    )
    assert isinstance(seeded, dict)
    chat_id = str(seeded.get("chat_id") or "")
    agent_id = str(seeded.get("agent_id") or "")
    assert chat_id.startswith("e2eslashchip")
    assert agent_id
    return seeded


_COMPOSER_READY_JS = """(() => ({
  ready:
    !!document.querySelector('[data-chat-input]') &&
    !!window.__MYRM_E2E_CHAT__ &&
    (window.__MYRM_E2E_CHAT__.turnSnapshot?.()?.agentSelectedSkillCount ?? 0) > 0,
  hasInput: !!document.querySelector('[data-chat-input]'),
  hasBridge: !!window.__MYRM_E2E_CHAT__,
}))()"""

_SKILL_PALETTE_ITEM_READY_JS = f"""(() => {{
  const palette = document.querySelector('[data-testid="slash-command-palette"]');
  if (!palette) return {{ ready: false, reason: 'no-palette' }};
  const needle = {json.dumps(_SLASH_QUERY)};
  const items = Array.from(palette.querySelectorAll('[cmdk-item], [role="option"]'));
  const target = items.find((el) => (el.textContent || '').toLowerCase().includes(needle));
  return {{
    ready: Boolean(target),
    itemCount: items.length,
  }};
}})()"""

_CLICK_SKILL_PALETTE_ITEM_JS = f"""(() => {{
  const palette = document.querySelector('[data-testid="slash-command-palette"]');
  if (!palette) return {{ ok: false, reason: 'no-palette' }};
  const needle = {json.dumps(_SLASH_QUERY)};
  const items = Array.from(palette.querySelectorAll('[cmdk-item], [role="option"]'));
  const target = items.find((el) => (el.textContent || '').toLowerCase().includes(needle));
  if (!target) return {{ ok: false, reason: 'no-skill-item' }};
  target.click();
  return {{ ok: true }};
}})()"""

_CHECK_CHIP_STRIP_MOUNTED_JS = """(() => {
  const strip = document.querySelector('[data-testid="composer-context-chip-strip"]');
  const chip = strip?.querySelector('[data-context-chip-id]');
  return {
    ready: Boolean(strip) && Boolean(chip),
    hasStrip: Boolean(strip),
    hasChip: Boolean(chip),
    chipText: chip ? chip.textContent : '',
  };
})()"""

_REMOVE_CHIP_VIA_BUTTON_JS = """(() => {
  const strip = document.querySelector('[data-testid="composer-context-chip-strip"]');
  if (!strip) return { ok: false, reason: 'strip-not-found' };
  const chip = strip.querySelector('[data-context-chip-id]');
  if (!chip) return { ok: false, reason: 'chip-not-found' };
  const removeBtn = chip.querySelector('button');
  if (!removeBtn) return { ok: false, reason: 'remove-btn-not-found', chipHtml: chip.outerHTML };
  removeBtn.click();
  return { ok: true };
})()"""

_CHECK_CHIP_REMOVED_JS = """(() => {
  const strip = document.querySelector('[data-testid="composer-context-chip-strip"]');
  const chip = strip?.querySelector('[data-context-chip-id]');
  return {
    ready: !strip && !chip,
    stripPresent: Boolean(strip),
    chipPresent: Boolean(chip),
  };
})()"""

_TRIGGER_BACKSPACE_ON_EMPTY_INPUT_JS = """(() => {
  const input = document.querySelector('[data-chat-input]');
  if (!input) return { ok: false, reason: 'input-not-found' };
  input.focus();
  input.setSelectionRange(0, 0);
  const event = new KeyboardEvent('keydown', {
    key: 'Backspace',
    code: 'Backspace',
    keyCode: 8,
    which: 8,
    bubbles: true,
    cancelable: true,
  });
  input.dispatchEvent(event);
  return { ok: true };
})()"""


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="READ",
    workload="STANDARD",
    private_reason="exclusive_backend",
)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_composer_inline_context_chip_strip_lifecycle_and_removal() -> None:
    """Validate ComposerContextChipStrip lifecycle: mount, click remove button, and Backspace removal."""
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(api_url)
    _ensure_skill_enabled(api_url, _SKILL_ID)
    seeded = _seed_composer_fixture(api_url)
    chat_id = str(seeded["chat_id"])
    agent_id = str(seeded["agent_id"])
    agent_chat_path = str(seeded.get("ui_path") or f"/{chat_id}?agentId={agent_id}")
    warm_ui_route(agent_chat_path)

    with open_mcp_page(f"{ui_url}{agent_chat_path}") as (client, page):
        wait_for_state(
            client,
            page,
            _COMPOSER_READY_JS,
            timeout_sec=_warm_ui_parallel_wait_sec(120.0),
        )

        def _pick_skill_from_palette() -> None:
            # 1. Type "/" to invoke palette
            typed = client.evaluate(
                page,
                f"""(() => {{
  const el = document.querySelector('[data-chat-input]');
  if (!el) return {{ ok: false, err: 'input-not-found' }};
  const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value')?.set;
  if (!setter) return {{ ok: false, err: 'setter-not-found' }};
  setter.call(el, {json.dumps("/" + _SLASH_QUERY)});
  el.setSelectionRange(el.value.length, el.value.length);
  el.dispatchEvent(new Event('input', {{ bubbles: true }}));
  el.dispatchEvent(new Event('change', {{ bubbles: true }}));
  return {{ ok: true, value: el.value }};
}})()""",
                timeout_sec=10.0,
            )
            assert isinstance(typed, dict) and typed.get("ok") is True, typed
            wait_for_state(
                client,
                page,
                _SKILL_PALETTE_ITEM_READY_JS,
                timeout_sec=_warm_ui_parallel_wait_sec(60.0),
            )
            clicked = client.evaluate(page, _CLICK_SKILL_PALETTE_ITEM_JS, timeout_sec=15.0)
            assert isinstance(clicked, dict) and clicked.get("ok") is True, clicked

        # Phase 1: Pick skill -> ComposerContextChipStrip mounts with SingleChip
        _pick_skill_from_palette()
        mounted = wait_for_state(
            client,
            page,
            _CHECK_CHIP_STRIP_MOUNTED_JS,
            timeout_sec=_warm_ui_parallel_wait_sec(30.0),
        )
        assert mounted.get("hasStrip") is True, mounted
        assert mounted.get("hasChip") is True, mounted

        # Phase 2: Click remove button on chip -> chip strip unmounts
        removed = client.evaluate(page, _REMOVE_CHIP_VIA_BUTTON_JS, timeout_sec=10.0)
        assert isinstance(removed, dict) and removed.get("ok") is True, removed
        state_after_btn = wait_for_state(
            client,
            page,
            _CHECK_CHIP_REMOVED_JS,
            timeout_sec=_warm_ui_parallel_wait_sec(30.0),
        )
        assert state_after_btn.get("stripPresent") is False, state_after_btn

        # Phase 3: Pick skill again -> Backspace on empty input removes chip
        _pick_skill_from_palette()
        wait_for_state(
            client,
            page,
            _CHECK_CHIP_STRIP_MOUNTED_JS,
            timeout_sec=_warm_ui_parallel_wait_sec(30.0),
        )
        bs_res = client.evaluate(page, _TRIGGER_BACKSPACE_ON_EMPTY_INPUT_JS, timeout_sec=10.0)
        assert isinstance(bs_res, dict) and bs_res.get("ok") is True, bs_res
        state_after_bs = wait_for_state(
            client,
            page,
            _CHECK_CHIP_REMOVED_JS,
            timeout_sec=_warm_ui_parallel_wait_sec(30.0),
        )
        assert state_after_bs.get("stripPresent") is False, state_after_bs
