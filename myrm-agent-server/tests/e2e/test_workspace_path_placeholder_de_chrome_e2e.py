"""Real Chrome E2E: the German workspace path placeholder fits the path popover, bound or not.

[INPUT]
- tests.support.chrome_mcp_e2e (POS: Chrome MCP test framework)
- myrm-agent-frontend NewTaskWorkContextCard (POS: empty-chat work context card with workspace path picker)
- myrm-agent-frontend locales/de.json chat.workspaceDir.placeholder (POS: the copy under test)

[OUTPUT]
- test_german_workspace_path_placeholder_fits_popover_chrome_e2e: the served German placeholder is the locale file's
  copy and is not clipped in either popover state

[POS]
Real-layout guard for localized copy in a fixed-width input. Rendered text width depends on the real font and the
input's geometry, which no jsdom test computes. The popover is `w-80`, so the field is narrowest once a workspace is
bound and the row gains a clear button; that state is measured first-class, not inferred.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.support.chrome_mcp_e2e import (
    get_e2e_api_url,
    get_e2e_ui_url,
    open_mcp_page,
    prepare_e2e_ui_session,
    reload_mcp_page,
    wait_for_state,
    warm_ui_route,
)

_LOCALE_FILE = Path(__file__).resolve().parents[3] / "myrm-agent-frontend" / "locales" / "de.json"
_LOCALE_COOKIE = "NEXT_LOCALE"
# NewTaskWorkContextCard remembers applied folders here; bound-state setup must not leave one behind.
_RECENT_DIRS_KEY = "myrm.workspaceDirPicker.recent"

_READ_BROWSER_STATE_JS = f"""(() => {{
  const hit = document.cookie.split('; ').find((c) => c.startsWith('{_LOCALE_COOKIE}='));
  return {{
    locale: hit ? hit.slice({len(_LOCALE_COOKIE) + 1}) : null,
    recent: localStorage.getItem({json.dumps(_RECENT_DIRS_KEY)}),
  }};
}})()"""


def _measure_js(*, bound: bool) -> str:
    """One idempotent step toward the wanted popover state, then the placeholder's fit once it is reached.

    Row order in the popover is `[back] input check [clear]`, and the clear button exists only while a workspace
    is bound, so the structure tells the state without relying on translated titles.
    """
    return f"""(() => {{
  const wantBound = {json.dumps(bound)};
  const card = document.querySelector('[data-testid="new-task-work-context-card"]');
  if (!card) return {{ ready: false, reason: 'no-card' }};
  const trigger = card.querySelector('[data-testid="workspace-picker-trigger"]');
  if (!trigger) {{
    const local = card.querySelector('[data-testid="context-mode-local"]');
    if (local) local.click();
    return {{ ready: false, reason: 'no-trigger' }};
  }}
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
    // Applying or clearing closes the popover; the next poll reopens it in the new state.
    const button = wantBound ? check : clear;
    if (button) button.click();
    return {{ ready: false, reason: 'switching-state', isBound }};
  }}
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


def _german_placeholder() -> str:
    copy = json.loads(_LOCALE_FILE.read_text(encoding="utf-8"))["chat"]["workspaceDir"]["placeholder"]
    assert isinstance(copy, str) and copy, copy
    return copy


def _width(state: dict[str, object], key: str) -> float:
    value = state.get(key)
    assert isinstance(value, (int, float)), json.dumps(state)
    return float(value)


@pytest.mark.chrome_e2e(
    execution_mode="SHARED",
    access_scope="READ",
    workload="STANDARD",
)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_german_workspace_path_placeholder_fits_popover_chrome_e2e() -> None:
    """The German placeholder must be fully visible with and without the clear button in the path row."""
    expected = _german_placeholder()
    prepare_e2e_ui_session(get_e2e_api_url())
    warm_ui_route("/")

    with open_mcp_page(f"{get_e2e_ui_url()}/") as (client, page):
        before = client.evaluate(page, _READ_BROWSER_STATE_JS, timeout_sec=15.0)
        assert isinstance(before, dict), before
        locale_before, recent_before = before.get("locale"), before.get("recent")
        locale_before = locale_before if isinstance(locale_before, str) else None
        recent_before = recent_before if isinstance(recent_before, str) else None
        try:
            client.evaluate(page, _set_browser_state_js(locale="de", recent=recent_before), timeout_sec=15.0)
            # A bare location.reload() returns at once and leaves the next evaluate racing the navigation.
            reload_mcp_page(client, page, timeout_ms=90_000)
            # Bound first: the sequence then ends unbound, leaving the page as the next test expects it.
            states = [wait_for_state(client, page, _measure_js(bound=bound), timeout_sec=90.0) for bound in (True, False)]
        finally:
            client.evaluate(page, _set_browser_state_js(locale=locale_before, recent=recent_before), timeout_sec=15.0)

    assert [state.get("bound") for state in states] == [True, False], json.dumps(states)
    for state in states:
        assert state.get("placeholder") == expected, json.dumps(state)
        assert _width(state, "textWidth") <= _width(state, "availableWidth"), json.dumps(state)
    # The clear button must really narrow the field, otherwise the narrowest state was never exercised.
    assert _width(states[0], "availableWidth") < _width(states[1], "availableWidth"), json.dumps(states)
