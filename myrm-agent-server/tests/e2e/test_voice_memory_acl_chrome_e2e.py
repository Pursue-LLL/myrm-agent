"""Chrome MCP E2E: Voice memory ACL Settings wiring (UI → personalSettings API)."""

from __future__ import annotations

import json
import time
from collections.abc import Iterator

import pytest

from tests.support.chrome_mcp_e2e import (
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_mcp_page,
    wait_for_state,
    warm_ui_route,
)
from tests.support.chrome_memory_settings_e2e import (
    ENABLE_MEMORY_JS,
    SETTINGS_SHELL_READY_JS,
    conversation_search_toggle_js,
)


def _config_value_snapshot(key: str) -> dict[str, object]:
    payload = http_json("GET", f"{get_e2e_api_url()}/api/v1/config/{key}")
    assert isinstance(payload, dict)
    value = payload.get("value")
    assert isinstance(value, dict)
    return value


def _put_personal_settings(value: dict[str, object]) -> None:
    http_json(
        "PUT",
        f"{get_e2e_api_url()}/api/v1/config/personalSettings",
        {"deviceId": "web", "value": value},
    )


def _ensure_voice_feature_enabled() -> None:
    http_json(
        "POST",
        f"{get_e2e_api_url()}/api/v1/features/voice_interaction/toggle",
        {"enabled": True},
    )


def _wait_personal_settings(
    *, enable_memory: bool, conversation_search: bool
) -> dict[str, object]:
    deadline = time.monotonic() + 30.0
    last: dict[str, object] = {}
    while time.monotonic() < deadline:
        last = _config_value_snapshot("personalSettings")
        memory_on = last.get("enableMemory") is True
        sessions_on = last.get("memoryEnableConversationSearch") is True
        if memory_on == enable_memory and sessions_on == conversation_search:
            return last
        time.sleep(0.5)
    raise AssertionError(
        json.dumps(
            {
                "err": "personal-settings-timeout",
                "expected": {
                    "enableMemory": enable_memory,
                    "memoryEnableConversationSearch": conversation_search,
                },
                "last": last,
            },
            ensure_ascii=False,
        )
    )


def _toggle_conversation_search(
    client, page, *, target_checked: bool
) -> dict[str, object]:
    deadline = time.monotonic() + 30.0
    last: dict[str, object] = {}
    script = conversation_search_toggle_js(target_checked=target_checked)
    while time.monotonic() < deadline:
        raw = client.evaluate(page, script, timeout_sec=10.0)
        last = raw if isinstance(raw, dict) else {"value": raw}
        if last.get("ok") is True:
            return last
        time.sleep(0.5)
    raise AssertionError(json.dumps(last, ensure_ascii=False))


@pytest.fixture(autouse=True)
def restore_personal_settings() -> Iterator[None]:
    snapshot = _config_value_snapshot("personalSettings")
    try:
        yield
    finally:
        _put_personal_settings(snapshot)


@pytest.fixture(autouse=True)
def voice_feature_enabled() -> None:
    _ensure_voice_feature_enabled()


@pytest.mark.chrome_e2e(lane="READ", private_backend=True)
@pytest.mark.timeout(240)
def test_voice_memory_settings_ui_enables_conversation_search_in_api() -> None:
    warm_ui_route("/settings/memory")
    ui_base = get_e2e_ui_url()
    with open_mcp_page(ui_base, timeout_ms=90_000) as (client, page):
        client.navigate(page, f"{ui_base}/settings/memory", timeout_ms=90_000)
        shell = wait_for_state(client, page, SETTINGS_SHELL_READY_JS, timeout_sec=90.0)
        assert shell.get("ready") is True, shell

        memory_on = client.evaluate(page, ENABLE_MEMORY_JS, timeout_sec=15.0)
        assert isinstance(memory_on, dict) and memory_on.get("ok") is True, memory_on
        time.sleep(1.0)

        toggled = _toggle_conversation_search(client, page, target_checked=True)
        assert toggled.get("ok") is True, toggled

    settings = _wait_personal_settings(enable_memory=True, conversation_search=True)
    assert settings.get("enableMemory") is True
    assert settings.get("memoryEnableConversationSearch") is True


@pytest.mark.chrome_e2e(lane="READ", private_backend=True)
@pytest.mark.timeout(240)
def test_voice_memory_settings_ui_disables_conversation_search_in_api() -> None:
    warm_ui_route("/settings/memory")
    ui_base = get_e2e_ui_url()
    with open_mcp_page(ui_base, timeout_ms=90_000) as (client, page):
        client.navigate(page, f"{ui_base}/settings/memory", timeout_ms=90_000)
        shell = wait_for_state(client, page, SETTINGS_SHELL_READY_JS, timeout_sec=90.0)
        assert shell.get("ready") is True, shell

        memory_on = client.evaluate(page, ENABLE_MEMORY_JS, timeout_sec=15.0)
        assert isinstance(memory_on, dict) and memory_on.get("ok") is True, memory_on
        time.sleep(1.0)

        _toggle_conversation_search(client, page, target_checked=True)
        _wait_personal_settings(enable_memory=True, conversation_search=True)

        toggled_off = _toggle_conversation_search(client, page, target_checked=False)
        assert toggled_off.get("ok") is True, toggled_off

        settings = _wait_personal_settings(
            enable_memory=True, conversation_search=False
        )
        assert settings.get("enableMemory") is True
        assert settings.get("memoryEnableConversationSearch") is False
