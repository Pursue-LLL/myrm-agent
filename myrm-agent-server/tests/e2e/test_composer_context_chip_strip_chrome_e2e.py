"""Real Chrome MCP E2E for ComposerInlineContextChipStrip unified lifecycle, overload, and real Task Flow.

Covers:
1. Lifecycle: slash palette selection, chip strip mount, non-empty text Backspace guard (prevent deletion),
   empty input Backspace shortcut removal, and button-click removal.
2. High-density & overload: multi-capability injection, desktop maxVisible threshold, "+N" overflow button,
   radix popover expansion, in-popover item removal, and amber overload nudge interaction.
3. Real Task Flow with real LLM (MiniMax-M3): slash skill selection, user prompt input,
   clean input UX with wire prefix serialization, send button click, automatic chip strip teardown,
   and receiving complete streaming assistant response from the real model.
"""

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
  const removeBtn = chip?.querySelector('button');
  const chatState = window.__myrmChatStore?.getState?.() || {};
  return {
    ready: Boolean(strip) && Boolean(chip) && Boolean(removeBtn),
    hasStrip: Boolean(strip),
    hasChip: Boolean(chip),
    hasButton: Boolean(removeBtn),
    chipText: chip ? chip.textContent : '',
    loading: Boolean(chatState.loading),
    isStreaming: Boolean(chatState.isStreaming),
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

_TRIGGER_BACKSPACE_ON_INPUT_JS = """(() => {
  const input = document.querySelector('[data-chat-input]');
  if (!input) return { ok: false, reason: 'input-not-found' };
  input.focus();
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

_SET_INPUT_TEXT_JS = """((text) => {
  const el = document.querySelector('[data-chat-input]');
  if (!el) return { ok: false, err: 'input-not-found' };
  const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value')?.set;
  if (!setter) return { ok: false, err: 'setter-not-found' };
  setter.call(el, text);
  el.setSelectionRange(el.value.length, el.value.length);
  el.dispatchEvent(new Event('input', { bubbles: true }));
  el.dispatchEvent(new Event('change', { bubbles: true }));
  return { ok: true, value: el.value };
})"""

_SET_MULTI_CAPABILITY_STATE_JS = """(() => {
  const store = window.__myrmChatStore?.getState?.();
  if (!store) return { ok: false, reason: 'no-store' };
  store.setPendingWorkflowTemplate('wf-e2e-demo', 'E2E Workflow');
  store.setPendingExplicitSkillActivation({
    skillNames: ['skill-1', 'skill-2', 'skill-3', 'skill-4', 'skill-5', 'skill-6'],
    instruction: 'multi capability overload test',
  });
  return { ok: true };
})()"""

_CHECK_OVERFLOW_AND_NUDGE_JS = """(() => {
  const strip = document.querySelector('[data-testid="composer-context-chip-strip"]');
  if (!strip) return { ready: false, reason: 'no-strip' };
  const chips = strip.querySelectorAll('[data-context-chip-id]');
  const buttons = Array.from(strip.querySelectorAll('button'));
  const overflowBtn = buttons.find((b) => /^\\+\\d+$/.test(b.textContent?.trim() || ''));
  const nudge = strip.querySelector('[data-testid="composer-overload-nudge"]');
  return {
    ready: Boolean(overflowBtn) && Boolean(nudge) && chips.length === 4,
    visibleChipCount: chips.length,
    hasOverflowBtn: Boolean(overflowBtn),
    overflowText: overflowBtn ? overflowBtn.textContent?.trim() : '',
    hasNudge: Boolean(nudge),
  };
})()"""

_CLICK_OVERFLOW_BTN_JS = """(() => {
  const strip = document.querySelector('[data-testid="composer-context-chip-strip"]');
  if (!strip) return { ok: false, reason: 'no-strip' };
  const buttons = Array.from(strip.querySelectorAll('button'));
  const overflowBtn = buttons.find((b) => /^\\+\\d+$/.test(b.textContent?.trim() || ''));
  if (!overflowBtn) return { ok: false, reason: 'no-overflow-btn' };
  overflowBtn.click();
  return { ok: true };
})()"""

_CHECK_POPOVER_OPEN_AND_REMOVE_ONE_JS = """(() => {
  const popoverWrapper = document.querySelector('[data-radix-popper-content-wrapper]');
  if (!popoverWrapper) return { ok: false, reason: 'no-popover' };
  const overflowChips = popoverWrapper.querySelectorAll('[data-context-chip-id]');
  if (overflowChips.length === 0) return { ok: false, reason: 'no-chips-in-popover' };
  const firstRemoveBtn = overflowChips[0].querySelector('button');
  if (!firstRemoveBtn) return { ok: false, reason: 'no-remove-btn-in-popover' };
  firstRemoveBtn.click();
  return { ok: true, removedCountBefore: overflowChips.length };
})()"""

_CLEAR_MULTI_CAPABILITY_STATE_JS = """(() => {
  const store = window.__myrmChatStore?.getState?.();
  if (!store) return { ok: false };
  store.clearPendingWorkflowTemplate();
  store.setPendingExplicitSkillActivation(null);
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
    """Validate ComposerContextChipStrip lifecycle, Backspace text-safety guard, and removal."""
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
            clicked = client.evaluate(
                page, _CLICK_SKILL_PALETTE_ITEM_JS, timeout_sec=15.0
            )
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

        # Phase 2: Edge Case Guard - Non-empty input Backspace must NEVER delete chip
        client.evaluate(
            page, f"({_SET_INPUT_TEXT_JS})('safety test')", timeout_sec=10.0
        )
        bs_guarded = client.evaluate(
            page, _TRIGGER_BACKSPACE_ON_INPUT_JS, timeout_sec=10.0
        )
        assert isinstance(bs_guarded, dict) and bs_guarded.get("ok") is True, bs_guarded

        # Verify chip strip is still mounted and intact
        guarded_check = client.evaluate(
            page, _CHECK_CHIP_STRIP_MOUNTED_JS, timeout_sec=10.0
        )
        assert isinstance(guarded_check, dict)
        assert (
            guarded_check.get("hasStrip") is True
        ), "Chip strip must NOT be removed when input has text"
        assert (
            guarded_check.get("hasChip") is True
        ), "Chip must NOT be removed when input has text"

        # Clear text so input becomes empty
        client.evaluate(page, f"({_SET_INPUT_TEXT_JS})('')", timeout_sec=10.0)

        # Phase 3: Empty input Backspace removes chip
        bs_res = client.evaluate(page, _TRIGGER_BACKSPACE_ON_INPUT_JS, timeout_sec=10.0)
        assert isinstance(bs_res, dict) and bs_res.get("ok") is True, bs_res
        state_after_bs = wait_for_state(
            client,
            page,
            _CHECK_CHIP_REMOVED_JS,
            timeout_sec=_warm_ui_parallel_wait_sec(30.0),
        )
        assert state_after_bs.get("stripPresent") is False, state_after_bs

        # Phase 4: Pick skill again -> Click remove button unmounts chip strip
        _pick_skill_from_palette()
        wait_for_state(
            client,
            page,
            _CHECK_CHIP_STRIP_MOUNTED_JS,
            timeout_sec=_warm_ui_parallel_wait_sec(30.0),
        )
        removed = client.evaluate(page, _REMOVE_CHIP_VIA_BUTTON_JS, timeout_sec=10.0)
        assert isinstance(removed, dict) and removed.get("ok") is True, removed
        state_after_btn = wait_for_state(
            client,
            page,
            _CHECK_CHIP_REMOVED_JS,
            timeout_sec=_warm_ui_parallel_wait_sec(30.0),
        )
        assert state_after_btn.get("stripPresent") is False, state_after_btn


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="READ",
    workload="STANDARD",
    private_reason="exclusive_backend",
)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_composer_context_chip_strip_overflow_popover_and_overload_nudge() -> None:
    """Validate high-density chip strip: maxVisible threshold, '+N' overflow popover, and amber overload badge."""
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(api_url)
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

        # 1. Inject high-density multi-capability payload (1 workflow + 6 skills = 7 chips)
        injected = client.evaluate(
            page, _SET_MULTI_CAPABILITY_STATE_JS, timeout_sec=10.0
        )
        assert isinstance(injected, dict) and injected.get("ok") is True, injected

        # 2. Wait for strip to render with 4 visible chips, "+3" overflow button, and amber overload nudge
        state = wait_for_state(
            client,
            page,
            _CHECK_OVERFLOW_AND_NUDGE_JS,
            timeout_sec=_warm_ui_parallel_wait_sec(30.0),
        )
        assert state.get("visibleChipCount") == 4, state
        assert state.get("hasOverflowBtn") is True, state
        assert state.get("overflowText") == "+3", state
        assert state.get("hasNudge") is True, state

        # 3. Click "+3" overflow button to open Radix Popover
        click_popover = client.evaluate(page, _CLICK_OVERFLOW_BTN_JS, timeout_sec=10.0)
        assert (
            isinstance(click_popover, dict) and click_popover.get("ok") is True
        ), click_popover

        # 4. Remove one chip inside the Popover
        removed_inside = client.evaluate(
            page, _CHECK_POPOVER_OPEN_AND_REMOVE_ONE_JS, timeout_sec=10.0
        )
        assert (
            isinstance(removed_inside, dict) and removed_inside.get("ok") is True
        ), removed_inside
        assert removed_inside.get("removedCountBefore") == 3, removed_inside

        # 5. Clean up multi-capability state
        cleaned = client.evaluate(
            page, _CLEAR_MULTI_CAPABILITY_STATE_JS, timeout_sec=10.0
        )
        assert isinstance(cleaned, dict) and cleaned.get("ok") is True, cleaned

        state_after_clean = wait_for_state(
            client,
            page,
            _CHECK_CHIP_REMOVED_JS,
            timeout_sec=_warm_ui_parallel_wait_sec(30.0),
        )
        assert state_after_clean.get("stripPresent") is False, state_after_clean


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="READ",
    workload="STANDARD",
    private_reason="exclusive_backend",
)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_composer_context_chip_send_turn_e2e_flow() -> None:
    """Validate real user Task Flow: slash pick, prompt typing, wire serialization, send click, and real model response."""
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

        # Pin SHPOIB direct-SSE so real UI send bypasses workspace multiplex bridge
        pinned = client.evaluate(
            page,
            """(() => { window.__MYRM_E2E_DIRECT_SSE__ = true; return true; })()""",
            timeout_sec=10.0,
        )
        assert pinned is True

        # Clear drafts
        client.evaluate(
            page,
            """(() => {
              for (let i = localStorage.length - 1; i >= 0; i--) {
                const key = localStorage.key(i);
                if (key && key.startsWith('myrm_draft_')) {
                  localStorage.removeItem(key);
                }
              }
              window.__MYRM_E2E_CHAT__?.setInputMessage?.('');
              return true;
            })()""",
            timeout_sec=10.0,
        )

        # 1. Type "/" to invoke palette and select skill
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

        wait_for_state(
            client,
            page,
            _CHECK_CHIP_STRIP_MOUNTED_JS,
            timeout_sec=_warm_ui_parallel_wait_sec(30.0),
        )

        # 2. Type real task prompt into input
        task_prompt = "请用中文只回复四个字：测试通过"
        client.evaluate(
            page, f"({_SET_INPUT_TEXT_JS})({json.dumps(task_prompt)})", timeout_sec=10.0
        )

        # 3. Assert wire message protocol carries [use systematic-debugging] prefix while input text is clean
        wire = client.evaluate(
            page,
            """(() => window.__MYRM_E2E_CHAT__?.peekOutboundUserMessage?.() ?? '')()""",
            timeout_sec=10.0,
        )
        assert isinstance(wire, str)
        assert wire.startswith(f"[use {_SKILL_ID}]"), wire
        assert task_prompt in wire

        # 4. Wait for send button to be ready and click it like a real user
        send_btn_ready = wait_for_state(
            client,
            page,
            """(() => {
              const btn = document.querySelector('.message-send-btn');
              return {
                ready: !!btn && !btn.disabled && btn.getAttribute('aria-disabled') !== 'true',
                disabled: btn?.disabled ?? null,
              };
            })()""",
            timeout_sec=15.0,
        )
        assert send_btn_ready.get("ready") is True, send_btn_ready

        btn_clicked = client.evaluate(
            page,
            """(() => {
              const btn = document.querySelector('.message-send-btn');
              if (!btn || btn.disabled) return false;
              btn.click();
              return true;
            })()""",
            timeout_sec=5.0,
        )
        assert btn_clicked is True, "Send button click failed"

        # 5. Assert input textarea cleared and composer chip strip unmounted
        wait_for_state(
            client,
            page,
            """(() => {
              const input = document.querySelector('[data-chat-input]');
              const strip = document.querySelector('[data-testid="composer-context-chip-strip"]');
              return {
                ready: !!input && input.value === '' && !strip,
                inputValue: input?.value ?? null,
                hasStrip: Boolean(strip),
              };
            })()""",
            timeout_sec=30.0,
        )

        # 6. Wait for real model response to arrive and finish streaming
        assistant_reply = wait_for_state(
            client,
            page,
            """(() => {
              const store = window.__myrmChatStore?.getState?.();
              const msgs = store?.messages ?? [];
              const assistantMsg = msgs.find(
                (m) => (m.role === 'assistant' || m.type === 'assistant') &&
                       String(m.content || m.text || '').trim().length > 0
              );
              const isStreaming = Boolean(store?.isStreaming || store?.loading);
              const content = String(assistantMsg?.content || assistantMsg?.text || '').trim();
              return {
                ready: Boolean(assistantMsg) && !isStreaming && content.length > 0,
                hasAssistantMsg: Boolean(assistantMsg),
                isStreaming,
                contentPreview: content.slice(0, 100),
                fullContent: content,
                totalMessages: msgs.length,
              };
            })()""",
            timeout_sec=180.0,
        )
        assert (
            assistant_reply.get("ready") is True
        ), f"Assistant reply failed or timed out: {assistant_reply}"
        response_text = str(assistant_reply.get("fullContent") or "")
        print(f"\nREAL_LLM_ASSISTANT_RESPONSE: {response_text}")
        assert len(response_text) > 0, "Model returned empty response"
