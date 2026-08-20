"""Chrome E2E: SecurityPreset live conversation, agent switch, and YOLO mutex.

Extends the READ chrome E2E (initialization / UI switch / fail-closed) with the
full real-user flows that need a real model and live state:

1. Live LLM conversation — a real message is sent while the bound agent's
   session preset is `accept_edits`; the assistant must reply and the session
   preset must stay `accept_edits` (the request path always carries
   `security_preset` in agent mode).
2. Agent switch reset — switching the bound agent must reset the session
   preset to the new agent's default (`accept_edits` -> `hitl`), i.e. no
   preset leaks across agents.
3. YOLO mutex (init path) — binding an agent whose default preset is
   `accept_edits` while YOLO mode is enabled must auto-disable YOLO
   (`disarmYoloForPreset`), keeping the safety invariant that non-HITL
   presets never coexist with YOLO.
4. Explore default preset — binding an agent whose default is `explore` must
   hydrate the session preset to `explore` (third-tier preset coverage).
5. YOLO + HITL coexistence — YOLO stays enabled when binding an agent whose
   default preset is `hitl`; only non-HITL presets disarm YOLO.
6. YOLO mutex (selector path) — with YOLO enabled, picking a preset through the
   real SecurityPresetSelector must disarm YOLO (`resolvePresetWithYoloMutex`)
   while updating the session preset.

Store-level assertions use `window.__myrmChatStore`; API-level assertions use
the PRIVATE backend directly so every UI reading is anchored by independent
server state.
"""

from __future__ import annotations

import json
import time

import pytest
from cdp_chat.support import (  # noqa: E402
    chat_user_message_count,
    fetch_chat_messages,
    fetch_config_value,
    put_config_value,
    shared_hot_e2e_api_base,
)

from tests.support.chrome_mcp_e2e import (
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_mcp_page,
    prepare_e2e_ui_session,
    wait_for_state,
    warm_ui_route,
)


def _seed_fixture(api_url: str) -> dict[str, str]:
    seeded = http_json(
        "POST",
        f"{api_url}/api/v1/chats/test/seed-security-preset-fixture",
    )
    assert isinstance(seeded, dict)
    for chat_key, agent_key, path_key in (
        ("preset_chat_id", "preset_agent_id", "preset_ui_path"),
        ("plain_chat_id", "plain_agent_id", "plain_ui_path"),
        ("explore_chat_id", "explore_agent_id", "explore_ui_path"),
    ):
        assert str(seeded.get(chat_key) or "").startswith("e2esecpreset")
        assert str(seeded.get(agent_key) or "")
        assert str(seeded.get(path_key) or "").startswith("/")
    return {key: str(seeded[key]) for key in seeded}


def _store_preset_probe(expected: str, agent_id: str | None = None) -> str:
    expected_json = json.dumps(expected)
    agent_json = json.dumps(agent_id) if agent_id else "null"
    return f"""(() => {{
  const store = window.__myrmChatStore?.getState?.();
  if (!store) return {{ ready: false, err: 'no-store' }};
  const preset = store.securityPreset;
  const boundAgentId = store.agentConfig?.agentId ?? null;
  const ready = preset === {expected_json}
    && ({agent_json} === null || boundAgentId === {agent_json});
  return {{
    ready,
    preset,
    expected: {expected_json},
    boundAgentId,
    expectedAgentId: {agent_json},
    actionMode: store.actionMode ?? null,
    apiBase: window.__MYRM_E2E_API_BASE__ ?? window.__MYRM_E2E_RUNTIME__?.apiBase ?? null,
    err: null,
  }};
}})()"""


def _fetch_config_resilient(config_key: str, api_url: str) -> dict[str, object]:
    last_exc: BaseException | None = None
    for attempt in range(5):
        try:
            value = fetch_config_value(config_key, api_url=api_url)
            return value if isinstance(value, dict) else {}
        except (OSError, TimeoutError) as exc:
            last_exc = exc
            if attempt + 1 >= 5:
                raise
            time.sleep(1.5 * (attempt + 1))
    assert last_exc is not None
    raise last_exc


def _mirror_shared_providers_to_private(api_url: str) -> None:
    """Mirror shared :8080 providers to the PRIVATE backend and pin the base
    model to the shared minimax provider when the shared openai-like default
    is unavailable in the test environment)."""
    try:
        shared = fetch_config_value("providers", api_url=shared_hot_e2e_api_base())
    except (OSError, TimeoutError) as exc:  # pragma: no cover - env dependent
        pytest.fail(f"shared :8080 providers unavailable: {exc}")
    if not isinstance(shared, dict) or not shared:
        pytest.fail("shared :8080 providers config is empty")

    providers = shared.get("providers")
    if not isinstance(providers, list) or not providers:
        pytest.fail("shared providers value has no providers list")
    minimax = next(
        (
            p
            for p in providers
            if isinstance(p, dict) and str(p.get("id")) == "minimax" and bool(p.get("isEnabled") or p.get("enabled"))
        ),
        None,
    )
    if not isinstance(minimax, dict):
        pytest.fail("shared providers have no enabled minimax provider")
    if not any(
        isinstance(k, dict) and k.get("isActive") and k.get("key")
        for k in (minimax.get("apiKeys") if isinstance(minimax.get("apiKeys"), list) else [])
    ):
        pytest.fail("shared minimax provider has no active API key")

    dmc = shared.get("defaultModelConfig")
    if not isinstance(dmc, dict):
        dmc = {}
    selection = {"providerId": "minimax", "model": "MiniMax-M3"}
    base = {"primary": selection, "fallback": None, "temperature": 0.7}
    dmc = dict(dmc)
    dmc["baseModel"] = base
    dmc["liteModel"] = {
        "primary": dict(selection),
        "fallback": None,
        "temperature": 0.7,
    }
    dmc["fastModeModel"] = None

    merged = dict(shared)
    merged["defaultModelConfig"] = dmc
    put_config_value("providers", merged, api_url=api_url)

    deadline = time.monotonic() + 20.0
    while time.monotonic() < deadline:
        value = _fetch_config_resilient("providers", api_url)
        saved_dmc = value.get("defaultModelConfig")
        if isinstance(saved_dmc, dict) and isinstance(saved_dmc.get("baseModel"), dict):
            primary = saved_dmc["baseModel"].get("primary")
            if isinstance(primary, dict) and primary.get("providerId") == "minimax" and primary.get("model") == "MiniMax-M3":
                return
        time.sleep(0.5)
    pytest.fail("minimax base model not persisted on PRIVATE backend")


def _set_yolo(api_url: str, enabled: bool) -> None:
    value = _fetch_config_resilient("securityConfig", api_url)
    value["yoloModeEnabled"] = enabled
    value["yolo_mode_enabled"] = enabled
    value["yoloModeEnabledAt"] = int(time.time() * 1000) if enabled else None
    value["yoloModeTimeout"] = None
    put_config_value("securityConfig", value, api_url=api_url)
    deadline = time.monotonic() + 20.0
    while time.monotonic() < deadline:
        current = bool(_fetch_config_resilient("securityConfig", api_url).get("yoloModeEnabled"))
        if current == enabled:
            return
        time.sleep(0.5)
    pytest.fail(f"yoloModeEnabled did not settle to {enabled} on PRIVATE backend")


def _wait_yolo_state(api_url: str, expected: bool, *, timeout_sec: float = 45.0) -> bool:
    deadline = time.monotonic() + timeout_sec
    last = not expected
    while time.monotonic() < deadline:
        last = bool(_fetch_config_resilient("securityConfig", api_url).get("yoloModeEnabled"))
        if last == expected:
            return last
        time.sleep(0.75)
    return last


def _attach_js(chat_id: str) -> str:
    chat_id_json = json.dumps(chat_id)
    return f"""(async () => {{
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge?.attachToChat) return {{ ok: false, err: 'no-bridge' }};
  await bridge.attachToChat({chat_id_json});
  const snap = bridge.turnSnapshot?.() ?? {{}};
  return {{ ok: snap.chatId === {chat_id_json}, chatId: snap.chatId ?? null }};
}})()"""


def _open_preset_selector_js() -> str:
    return """(() => {
  const target = document.querySelector('[data-testid="security-preset-trigger"]');
  if (!target) return { ok: false, err: 'no-trigger' };
  const opts = { bubbles: true, cancelable: true, composed: true, button: 0 };
  target.dispatchEvent(new PointerEvent('pointerdown', opts));
  target.dispatchEvent(new MouseEvent('mousedown', opts));
  target.dispatchEvent(new PointerEvent('pointerup', opts));
  target.dispatchEvent(new MouseEvent('mouseup', opts));
  target.dispatchEvent(new MouseEvent('click', opts));
  return { ok: true };
})()"""


def _pick_preset_option_js(preset: str) -> str:
    preset_json = json.dumps(preset)
    return f"""(() => {{
  const option = document.querySelector(
    '[data-testid="security-preset-option-{preset}"]'
  );
  if (!option) return {{ ok: false, err: 'no-option', preset: {preset_json} }};
  const opts = {{ bubbles: true, cancelable: true, composed: true, button: 0 }};
  option.dispatchEvent(new PointerEvent('pointerdown', opts));
  option.dispatchEvent(new MouseEvent('mousedown', opts));
  option.dispatchEvent(new PointerEvent('pointerup', opts));
  option.dispatchEvent(new MouseEvent('mouseup', opts));
  option.dispatchEvent(new MouseEvent('click', opts));
  return {{ ok: true, preset: {preset_json} }};
}})()"""


def _send_turn_js(prompt: str) -> str:
    prompt_json = json.dumps(prompt)
    return f"""(async () => {{
  window.__MYRM_E2E_DIRECT_SSE__ = true;
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge?.sendChatMessage) return {{ ok: false, err: 'no-sendChatMessage' }};
  bridge.setActionMode?.('agent');
  const usersBefore = bridge.turnSnapshot?.().userCount ?? 0;
  const result = await bridge.sendChatMessage({prompt_json}, {{
    baselineUserCount: usersBefore,
    waitForStreamCompletion: false,
    preserveActionMode: true,
  }});
  return {{ ...result, usersBefore }};
}})()"""


def _wait_assistant_reply(
    chat_id: str,
    api_url: str,
    *,
    timeout_sec: float = 150.0,
) -> dict[str, object]:
    deadline = time.monotonic() + timeout_sec
    last: dict[str, object] = {}
    last_messages: list[dict[str, object]] = []
    while time.monotonic() < deadline:
        try:
            messages = fetch_chat_messages(chat_id, api_url=api_url)
        except OSError:
            messages = []
        last_messages = [m for m in messages if isinstance(m, dict) and m.get("role") in ("user", "assistant")]
        assistant = next(
            (m for m in reversed(last_messages) if isinstance(m, dict) and m.get("role") == "assistant"),
            None,
        )
        if isinstance(assistant, dict):
            content = assistant.get("content") or assistant.get("message") or ""
            if isinstance(content, str) and content.strip():
                return assistant
        last = assistant or {}
        time.sleep(2.0)
    pytest.fail(
        f"assistant reply not received within {timeout_sec}s for chat {chat_id}; "
        f"last={json.dumps(last, ensure_ascii=False)[:300]} "
        f"messages={json.dumps(last_messages, ensure_ascii=False)[:800]}"
    )


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="STANDARD",
    private_reason="exclusive_backend",
)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_security_preset_live_flow_and_switch_and_yolo_mutex() -> None:
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(api_url)
    _mirror_shared_providers_to_private(api_url)
    seeded = _seed_fixture(api_url)
    preset_path = seeded["preset_ui_path"]
    plain_path = seeded["plain_ui_path"]
    preset_chat_id = seeded["preset_chat_id"]
    preset_agent_id = seeded["preset_agent_id"]
    plain_agent_id = seeded["plain_agent_id"]

    # --- Scenario 1: live LLM conversation keeps accept_edits preset ---
    warm_ui_route(preset_path)
    with open_mcp_page(f"{ui_url}{preset_path}", timeout_ms=120_000) as (client, page):
        init_state = wait_for_state(
            client,
            page,
            _store_preset_probe("accept_edits", preset_agent_id),
            timeout_sec=90.0,
        )
        assert init_state.get("ready") is True, json.dumps(init_state, ensure_ascii=False)

        attached = client.evaluate(page, _attach_js(preset_chat_id), timeout_sec=30.0)
        assert isinstance(attached, dict) and attached.get("ok") is True, attached

        send = client.evaluate(
            page,
            _send_turn_js("Please reply with one short sentence introducing yourself."),
            timeout_sec=60.0,
        )
        assert isinstance(send, dict), send
        assert send.get("ok") is True, json.dumps(send, ensure_ascii=False)
        assert send.get("chatId") in (preset_chat_id, None), json.dumps(send, ensure_ascii=False)

        reply = _wait_assistant_reply(preset_chat_id, api_url, timeout_sec=120.0)
        assert str(reply.get("role")) == "assistant"

        after_turn = wait_for_state(
            client,
            page,
            _store_preset_probe("accept_edits", preset_agent_id),
            timeout_sec=30.0,
        )
        assert after_turn.get("ready") is True, json.dumps(after_turn, ensure_ascii=False)

    # --- Scenario 2: agent switch resets preset (no leak across agents) ---
    warm_ui_route(plain_path)
    with open_mcp_page(f"{ui_url}{plain_path}", timeout_ms=120_000) as (client, page):
        switch_state = wait_for_state(
            client,
            page,
            _store_preset_probe("hitl", plain_agent_id),
            timeout_sec=90.0,
        )
        assert switch_state.get("ready") is True, json.dumps(switch_state, ensure_ascii=False)

    warm_ui_route(preset_path)
    with open_mcp_page(f"{ui_url}{preset_path}", timeout_ms=120_000) as (client, page):
        back_state = wait_for_state(
            client,
            page,
            _store_preset_probe("accept_edits", preset_agent_id),
            timeout_sec=90.0,
        )
        assert back_state.get("ready") is True, json.dumps(back_state, ensure_ascii=False)

    # --- Scenario 3: binding a non-HITL preset agent auto-disables YOLO ---
    _set_yolo(api_url, True)
    assert _wait_yolo_state(api_url, True, timeout_sec=20.0) is True

    warm_ui_route(preset_path)
    with open_mcp_page(f"{ui_url}{preset_path}", timeout_ms=120_000) as (client, page):
        yolo_init_state = wait_for_state(
            client,
            page,
            _store_preset_probe("accept_edits", preset_agent_id),
            timeout_sec=90.0,
        )
        assert yolo_init_state.get("ready") is True, json.dumps(yolo_init_state, ensure_ascii=False)

    yolo_off = _wait_yolo_state(api_url, False, timeout_sec=45.0)
    assert yolo_off is False, "YOLO must be auto-disabled after binding accept_edits agent"

    # --- Scenario 4: explore default preset hydrates to explore (third tier) ---
    explore_path = seeded["explore_ui_path"]
    explore_agent_id = seeded["explore_agent_id"]
    warm_ui_route(explore_path)
    with open_mcp_page(f"{ui_url}{explore_path}", timeout_ms=120_000) as (client, page):
        explore_state = wait_for_state(
            client,
            page,
            _store_preset_probe("explore", explore_agent_id),
            timeout_sec=90.0,
        )
        assert explore_state.get("ready") is True, json.dumps(explore_state, ensure_ascii=False)

    # --- Scenario 5: HITL preset coexists with YOLO (only non-HITL disarms) ---
    _set_yolo(api_url, True)
    assert _wait_yolo_state(api_url, True, timeout_sec=20.0) is True

    warm_ui_route(plain_path)
    with open_mcp_page(f"{ui_url}{plain_path}", timeout_ms=120_000) as (client, page):
        hitl_state = wait_for_state(
            client,
            page,
            _store_preset_probe("hitl", plain_agent_id),
            timeout_sec=90.0,
        )
        assert hitl_state.get("ready") is True, json.dumps(hitl_state, ensure_ascii=False)

    yolo_still_on = _wait_yolo_state(api_url, True, timeout_sec=20.0)
    assert yolo_still_on is True, "YOLO must stay enabled with a hitl default agent"

    # --- Scenario 6: selector path also disarms YOLO (resolvePresetWithYoloMutex) ---
    # YOLO is still enabled after Scenario 5 (hitl agent does not disarm it).
    warm_ui_route(plain_path)
    with open_mcp_page(f"{ui_url}{plain_path}", timeout_ms=120_000) as (client, page):
        hitl_ready = wait_for_state(
            client,
            page,
            _store_preset_probe("hitl", plain_agent_id),
            timeout_sec=90.0,
        )
        assert hitl_ready.get("ready") is True, json.dumps(hitl_ready, ensure_ascii=False)

        yolo_synced = _wait_yolo_state(api_url, True, timeout_sec=30.0)
        assert yolo_synced is True, "YOLO should still be on before the selector pick"

        opened = client.evaluate(page, _open_preset_selector_js(), timeout_sec=15.0)
        assert isinstance(opened, dict) and opened.get("ok") is True, opened

        option_ready = wait_for_state(
            client,
            page,
            """(() => {
  const option = document.querySelector('[data-testid="security-preset-option-accept_edits"]');
  return { ready: !!option };
})()""",
            timeout_sec=15.0,
        )
        assert option_ready.get("ready") is True, json.dumps(option_ready, ensure_ascii=False)

        picked = client.evaluate(
            page,
            _pick_preset_option_js("accept_edits"),
            timeout_sec=15.0,
        )
        assert isinstance(picked, dict) and picked.get("ok") is True, picked

        after_pick = wait_for_state(
            client,
            page,
            _store_preset_probe("accept_edits", plain_agent_id),
            timeout_sec=30.0,
        )
        assert after_pick.get("ready") is True, json.dumps(after_pick, ensure_ascii=False)

    yolo_disarmed = _wait_yolo_state(api_url, False, timeout_sec=45.0)
    assert yolo_disarmed is False, "YOLO must be disabled after selector picks accept_edits"

    # Sanity: the live turn really persisted both a user and an assistant message.
    users = chat_user_message_count(preset_chat_id, api_url=api_url)
    assert users >= 1, f"expected a persisted user message, got {users}"
