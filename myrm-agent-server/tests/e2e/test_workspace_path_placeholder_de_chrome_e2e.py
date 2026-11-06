"""Real Chrome E2E: the German workspace path placeholder fits both path popovers, bound or not.

[INPUT]
- tests.support.chrome_mcp_e2e (POS: Chrome MCP test framework)
- myrm-agent-frontend WorkspaceDirPicker (POS: the single workspace row under the composer, on every viewport)
- myrm-agent-frontend locales/de.json chat.workspaceDir (POS: the copy under test)

[OUTPUT]
- test_german_workspace_path_placeholder_fits_empty_chat_picker_chrome_e2e: the row's popover on the empty chat
  shows the locale file's placeholder unclipped in both states
- test_german_workspace_path_placeholder_fits_chat_picker_chrome_e2e: the same row does the same on a seeded chat

[POS]
Real-layout guard for localized copy in a fixed-width input. Rendered text width depends on the real font and the
input's geometry, which no jsdom test computes. Both popovers are `w-80`, so the field is narrowest once a workspace
is bound and the row gains a clear button; that state is measured first-class, not inferred.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from tests.support.chrome_mcp_e2e import (
    ChromeMcpClient,
    McpPage,
    dismiss_blocking_modals,
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_mcp_page,
    prepare_e2e_ui_session,
    reload_mcp_page,
    wait_for_react_e2e_bridge,
    wait_for_state,
    warm_ui_route,
)

_LOCALE_FILE = Path(__file__).resolve().parents[3] / "myrm-agent-frontend" / "locales" / "de.json"
_LOCALE_COOKIE = "NEXT_LOCALE"
# Both pickers remember applied folders here; bound-state setup must not leave one behind.
_RECENT_DIRS_KEY = "myrm.workspaceDirPicker.recent"

_READ_BROWSER_STATE_JS = f"""(() => {{
  const hit = document.cookie.split('; ').find((c) => c.startsWith('{_LOCALE_COOKIE}='));
  return {{
    locale: hit ? hit.slice({len(_LOCALE_COOKIE) + 1}) : null,
    recent: localStorage.getItem({json.dumps(_RECENT_DIRS_KEY)}),
  }};
}})()"""

# The workspace row has one render site on every viewport; the seeded chat only needs agent mode.
_WORKSPACE_TRIGGER = "workspace-dir-trigger"
_EMPTY_CHAT_TRIGGER_JS = f"""return document.querySelector('[data-testid="{_WORKSPACE_TRIGGER}"]');"""


def _chat_picker_trigger_js() -> str:
    return f"""window.__MYRM_E2E_CHAT__?.setActionMode?.('agent');
    return document.querySelector('[data-testid="{_WORKSPACE_TRIGGER}"]');"""


def _measure_js(*, bound: bool, find_trigger: str) -> str:
    """One idempotent step toward the wanted popover state, then the placeholder's fit once it is reached.

    Row order in the popover is `[back] input check [clear]`, and the clear button exists only while a workspace
    is bound, so the structure tells the state without relying on translated titles.
    """
    return f"""(() => {{
  const wantBound = {json.dumps(bound)};
  const findTrigger = () => {{
    {find_trigger}
  }};
  const trigger = findTrigger();
  if (!trigger) return {{ ready: false, reason: 'no-trigger' }};
  // A closing popover lingers in the DOM while the parked tab never finishes its exit animation, so only
  // aria-expanded says whether the content on screen is current.
  if (trigger.getAttribute('aria-expanded') !== 'true') {{
    trigger.click();
    return {{ ready: false, reason: 'popover-closed' }};
  }}
  const input = document.querySelector('[data-radix-popper-content-wrapper] input');
  // The directory listing fills the input; the back button appears with it, so the width is final only then.
  if (!input || !input.value) return {{ ready: false, reason: 'browse-loading' }};
  const check = input.nextElementSibling;
  const clear = check ? check.nextElementSibling : null;
  const isBound = Boolean(clear);
  if (isBound !== wantBound) {{
    // Applying or clearing closes the popover; the next poll reopens it in the new state. A change the server
    // refuses must not be retried for the whole wait, so the attempts are capped.
    window.__wsphSwitchClicks = (window.__wsphSwitchClicks || 0) + 1;
    if (window.__wsphSwitchClicks > 10) return {{ ready: false, reason: 'switch-refused', isBound }};
    const button = wantBound ? check : clear;
    if (button) button.click();
    return {{ ready: false, reason: 'switching-state', isBound }};
  }}
  window.__wsphSwitchClicks = 0;
  const style = getComputedStyle(input);
  // Text renders in the first family once its face is loaded. `document.fonts.check` would also wait for the
  // list's fallback face, which is never needed after that and stays unloaded for good.
  const unquote = (name) => name.trim().replace(/^["']|["']$/g, '');
  const primary = unquote(style.fontFamily.split(',')[0]);
  const faces = Array.from(document.fonts).filter((face) => unquote(face.family) === primary);
  if (faces.length > 0 && !faces.some((face) => face.status === 'loaded')) {{
    return {{ ready: false, reason: 'fonts-loading', primary, faces: faces.map((face) => face.status) }};
  }}
  const canvas = document.createElement('canvas').getContext('2d');
  canvas.font = style.font;
  return {{
    ready: true,
    bound: isBound,
    trigger: trigger.getAttribute('data-testid') || trigger.title,
    placeholder: input.placeholder,
    textWidth: canvas.measureText(input.placeholder).width,
    availableWidth: input.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight),
    font: primary + ' ' + style.fontSize,
    viewportWidth: window.innerWidth,
  }};
}})()"""


def _set_browser_state_js(*, locale: str | None, recent: str | None) -> str:
    """Write the language cookie as the picker does, and the remembered-folders entry (None removes it)."""
    cookie = f"{_LOCALE_COOKIE}={locale}; path=/; max-age=31536000" if locale else f"{_LOCALE_COOKIE}=; path=/; max-age=0"
    key = json.dumps(_RECENT_DIRS_KEY)
    recent_stmt = (
        f"localStorage.setItem({key}, {json.dumps(recent)});" if recent is not None else f"localStorage.removeItem({key});"
    )
    return f"(() => {{ document.cookie = {json.dumps(cookie)}; {recent_stmt} return {{ ok: true }}; }})()"


def _german_copy(key: str) -> str:
    copy = json.loads(_LOCALE_FILE.read_text(encoding="utf-8"))["chat"]["workspaceDir"][key]
    assert isinstance(copy, str) and copy, copy
    return copy


@contextmanager
def _german_locale(client: ChromeMcpClient, page: McpPage) -> Iterator[None]:
    """Show the open page in German through the language cookie; the browser's locale and folders are restored after."""
    before = client.evaluate(page, _READ_BROWSER_STATE_JS, timeout_sec=15.0)
    assert isinstance(before, dict), before
    locale_before, recent_before = before.get("locale"), before.get("recent")
    locale_before = locale_before if isinstance(locale_before, str) else None
    recent_before = recent_before if isinstance(recent_before, str) else None
    try:
        client.evaluate(page, _set_browser_state_js(locale="de", recent=recent_before), timeout_sec=15.0)
        # A bare location.reload() returns at once and leaves the next evaluate racing the navigation.
        reload_mcp_page(client, page, timeout_ms=90_000)
        yield
    finally:
        client.evaluate(page, _set_browser_state_js(locale=locale_before, recent=recent_before), timeout_sec=15.0)


def _measure_both_states(client: ChromeMcpClient, page: McpPage, find_trigger: str) -> list[dict[str, object]]:
    """Bound first, unbound last: an opened chat starts bound and the server refuses to bind it again to the
    browse root, while the empty chat starts unbound and so ends the way it began."""
    return [
        wait_for_state(client, page, _measure_js(bound=bound, find_trigger=find_trigger), timeout_sec=90.0)
        for bound in (True, False)
    ]


def _width(state: dict[str, object], key: str) -> float:
    value = state.get(key)
    assert isinstance(value, (int, float)), json.dumps(state)
    return float(value)


def _assert_placeholder_fits(states: list[dict[str, object]], *, expected: str, trigger: str) -> None:
    assert [state.get("bound") for state in states] == [True, False], json.dumps(states)
    for state in states:
        assert state.get("trigger") == trigger, json.dumps(state)
        assert state.get("placeholder") == expected, json.dumps(state)
        assert _width(state, "textWidth") <= _width(state, "availableWidth"), json.dumps(state)
    # The clear button must really narrow the field, otherwise the narrowest state was never exercised.
    assert _width(states[0], "availableWidth") < _width(states[1], "availableWidth"), json.dumps(states)


@pytest.mark.chrome_e2e(
    execution_mode="SHARED",
    access_scope="READ",
    workload="STANDARD",
)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_german_workspace_path_placeholder_fits_empty_chat_picker_chrome_e2e() -> None:
    """On the empty chat the German placeholder is fully visible with and without the clear button."""
    expected = _german_copy("placeholder")
    prepare_e2e_ui_session(get_e2e_api_url())
    warm_ui_route("/")

    with open_mcp_page(f"{get_e2e_ui_url()}/") as (client, page), _german_locale(client, page):
        states = _measure_both_states(client, page, _EMPTY_CHAT_TRIGGER_JS)

    _assert_placeholder_fits(states, expected=expected, trigger=_WORKSPACE_TRIGGER)


_ATTACH_CHAT_JS = """(() => {{
  const bridge = window.__MYRM_E2E_CHAT__;
  const store = window.__myrmChatStore?.getState?.();
  const attached =
    store?.chatId === {chat_id_json}
    && Boolean(store?.isMessagesLoaded)
    && !Boolean(store?.loadError)
    && !Boolean(store?.notFound);
  if (attached) return {{ ready: true, chatId: store?.chatId ?? null }};
  if (bridge?.attachToChat && !window.__MYRM_E2E_ATTACHING__) {{
    window.__MYRM_E2E_ATTACHING__ = true;
    bridge.attachToChat({chat_id_json}).catch(() => {{}}).finally(() => {{
      window.__MYRM_E2E_ATTACHING__ = false;
    }});
  }}
  return {{ ready: false, chatId: store?.chatId ?? null, err: bridge ? null : 'no-bridge' }};
}})()"""


def _seed_chat(api_url: str) -> str:
    """One finished exchange, so the chat view (and its message input toolbar) renders without any model turn.

    Opening a chat binds it to its own sandbox folder (`resolve_effective_chat_workspace` falls back to it), so
    the picker starts bound. The unbound state is reached with the clear button: the server refuses broad folders
    such as the home directory, which is what the picker would offer when binding again.
    """
    chat_id = f"e2ewsph{uuid.uuid4().hex[:8]}"
    now = datetime.now(UTC).replace(microsecond=0)
    messages = [
        {"messageId": f"msg-user-{chat_id}", "chatId": chat_id, "role": "user", "content": "Hallo", "createdAt": now.isoformat()},
        {
            "messageId": f"msg-asst-{chat_id}",
            "chatId": chat_id,
            "role": "assistant",
            "content": "Hallo!",
            "createdAt": (now + timedelta(seconds=1)).isoformat(),
        },
    ]
    created = http_json(
        "POST",
        f"{api_url}/api/v1/chats/",
        body={
            "chat_id": chat_id,
            "title": "E2E workspace path placeholder",
            "action_mode": "agent",
            "is_incognito": False,
            "messages": messages,
        },
    )
    assert isinstance(created, dict) and created.get("success") is True, created
    return chat_id


@pytest.mark.chrome_e2e(
    execution_mode="SHARED",
    access_scope="NAMESPACE_WRITE",
    workload="STANDARD",
)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_german_workspace_path_placeholder_fits_chat_picker_chrome_e2e() -> None:
    """In an open chat the German placeholder is fully visible with and without the clear button."""
    expected = _german_copy("placeholder")
    api_url = get_e2e_api_url()
    prepare_e2e_ui_session(api_url)
    chat_id = _seed_chat(api_url)
    chat_url = f"{get_e2e_ui_url()}/{chat_id}"

    try:
        warm_ui_route(f"/{chat_id}")
        with open_mcp_page(chat_url, timeout_ms=120_000) as (client, page):
            dismiss_blocking_modals(client, page, recover_url=chat_url)
            with _german_locale(client, page):
                bridge = wait_for_react_e2e_bridge(client, page, timeout_sec=90.0, page_url=chat_url)
                assert bridge.get("ready") is True, bridge
                attached = wait_for_state(
                    client, page, _ATTACH_CHAT_JS.format(chat_id_json=json.dumps(chat_id)), timeout_sec=90.0, page_url=chat_url
                )
                assert attached.get("ready") is True, attached
                states = _measure_both_states(client, page, _chat_picker_trigger_js())
    finally:
        # Best-effort cleanup of the seeded chat on the backend it was created in.
        try:
            http_json("DELETE", f"{api_url}/api/v1/chats/{chat_id}")
        except (RuntimeError, OSError, ValueError):
            pass

    _assert_placeholder_fits(states, expected=expected, trigger=_WORKSPACE_TRIGGER)
