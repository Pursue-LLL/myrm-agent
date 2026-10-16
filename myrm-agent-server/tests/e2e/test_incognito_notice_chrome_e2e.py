"""Chrome E2E: switching incognito mode on states its terms on the empty chat, in a real browser.

Incognito is client state (no backend write), so the lane is SHARED+READ. The toggle is clicked the way a user does;
the notice must appear, stay readable in both themes (WCAG AA text contrast), fit a phone-width window without
widening the page, and disappear again when switched off.

Formal run::

    ./myrm test -m chrome_e2e \\
      myrm-agent/myrm-agent-server/tests/e2e/test_incognito_notice_chrome_e2e.py
"""

from __future__ import annotations

import pytest

from tests.support.chrome_mcp_e2e import (
    _warm_ui_parallel_wait_sec,
    dismiss_blocking_modals,
    ensure_desktop_viewport,
    get_e2e_api_url,
    get_e2e_ui_url,
    open_mcp_page,
    prepare_e2e_ui_session,
    wait_for_state,
    warm_ui_route,
)

# The toggle's accessible name in every shipped locale (memory.incognitoMode).
_TOGGLE_LABELS = ("Incognito Mode", "无痕模式", "無痕模式", "シークレットモード", "시크릿 모드", "Inkognito-Modus")

_FIND_TOGGLE = """const labels = %s;
  const toggle = Array.from(document.querySelectorAll('button[aria-pressed]')).find(
    (el) => labels.includes(el.getAttribute('aria-label') || '') && el.offsetParent !== null,
  );""" % list(_TOGGLE_LABELS)

_TOGGLE_READY = f"""(() => {{
  {_FIND_TOGGLE}
  // A click before React attached its handlers is lost, and the notice is rendered by the same component as the
  // empty-chat heading, so both have to be hydrated before the toggle counts.
  const heading = document.querySelector('[data-testid="empty-chat-title"]');
  const isHydrated = (el) => !!el && Object.keys(el).some((key) => key.startsWith('__reactProps'));
  const hydrated = isHydrated(toggle) && isHydrated(heading);
  return {{
    ready: !!toggle && hydrated && !document.querySelector('[data-testid="incognito-notice"]'),
    hydrated,
    pressed: toggle ? toggle.getAttribute('aria-pressed') : null,
  }};
}})()"""

_CLICK_TOGGLE = f"""(() => {{
  {_FIND_TOGGLE}
  if (!toggle) {{
    return {{ clicked: false }};
  }}
  window.__incognitoClickedAt = performance.now();
  toggle.click();
  return {{ clicked: true }};
}})()"""

_NOTICE_STATE = f"""(() => {{
  {_FIND_TOGGLE}
  const notice = document.querySelector('[data-testid="incognito-notice"]');
  if (!notice) {{
    return {{
      ready: false,
      pressed: toggle ? toggle.getAttribute('aria-pressed') : null,
      storeIncognito: window.__myrmChatStore?.getState?.().incognitoMode ?? null,
    }};
  }}
  const box = notice.getBoundingClientRect();
  const doc = document.documentElement;
  return {{
    ready: true,
    latencyMs: Math.round(performance.now() - (window.__incognitoClickedAt ?? performance.now())),
    textLength: (notice.textContent || '').trim().length,
    insideViewport: box.left >= 0 && box.right <= window.innerWidth,
    pageOverflowsX: doc.scrollWidth > doc.clientWidth,
  }};
}})()"""

_NOTICE_GONE = f"""(() => {{
  {_FIND_TOGGLE}
  return {{
    ready: !document.querySelector('[data-testid="incognito-notice"]'),
    pressed: toggle ? toggle.getAttribute('aria-pressed') : null,
    storeIncognito: window.__myrmChatStore?.getState?.().incognitoMode ?? null,
    frames: document.querySelectorAll('iframe').length,
  }};
}})()"""

# Text contrast as the user sees it: every background in the ancestor chain and the text itself are composited on a
# canvas, which resolves whatever color syntax the theme variables use, then WCAG relative luminance is compared.
_CONTRAST_JS = """(() => {
  const notice = document.querySelector('[data-testid="incognito-notice"]');
  if (!notice) {
    return { ready: false };
  }
  const root = document.documentElement;
  if (!document.getElementById('e2e-no-transition')) {
    // Colors are transitioned, so a measurement right after the class swap would read the previous theme.
    const style = document.createElement('style');
    style.id = 'e2e-no-transition';
    style.textContent = '*, *::before, *::after { transition: none !important; }';
    (document.head || document.documentElement).appendChild(style);
  }
  root.classList.remove('light', 'dark');
  root.classList.add('__THEME__');
  const ctx = document.createElement('canvas').getContext('2d', { willReadFrequently: true });
  const paint = (css) => {
    ctx.fillStyle = css;
    ctx.fillRect(0, 0, 1, 1);
  };
  const pixel = () => Array.from(ctx.getImageData(0, 0, 1, 1).data).slice(0, 3);
  const chain = [];
  for (let el = notice; el; el = el.parentElement) {
    chain.unshift(el);
  }
  paint('#ffffff');
  for (const el of chain) {
    paint(getComputedStyle(el).backgroundColor);
  }
  const background = pixel();
  const luminance = ([r, g, b]) => {
    const [lr, lg, lb] = [r, g, b].map((v) => {
      const c = v / 255;
      return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
    });
    return 0.2126 * lr + 0.7152 * lg + 0.0722 * lb;
  };
  const contrast = (el) => {
    const [r, g, b] = background;
    paint('rgb(' + r + ',' + g + ',' + b + ')');
    paint(getComputedStyle(el).color);
    const text = pixel();
    const hi = Math.max(luminance(background), luminance(text));
    const lo = Math.min(luminance(background), luminance(text));
    return { ratio: (hi + 0.05) / (lo + 0.05), text, background };
  };
  const [title, body] = notice.querySelectorAll('span.block');
  return { ready: true, theme: '__THEME__', title: contrast(title), body: contrast(body) };
})()"""

# A phone-sized same-origin frame gives the app a real 390px viewport (window.resizeTo is a no-op in this Chrome),
# so its media queries pick the phone layout; there the toggle sits in a bottom sheet, so the store flips the mode.
# The frame is a second full app load: on a cold dev server its empty-chat chunk can take a minute to hydrate.
_PHONE_FRAME_WIDTH = 390
_PHONE_FRAME_STATE = """(() => {
  let frame = document.getElementById('e2e-phone-frame');
  if (!frame) {
    frame = document.createElement('iframe');
    frame.id = 'e2e-phone-frame';
    frame.style.cssText = 'position:fixed;left:0;top:0;width:390px;height:844px;border:0;z-index:2147483647;background:#fff';
    frame.src = location.origin + '/';
    document.body.appendChild(frame);
    return { ready: false, stage: 'loading' };
  }
  const win = frame.contentWindow;
  const doc = win.document;
  const store = win.__myrmChatStore;
  const heading = doc.querySelector('[data-testid="empty-chat-title"]');
  const hydrated = !!heading && Object.keys(heading).some((key) => key.startsWith('__reactProps'));
  if (!store || !hydrated) {
    return { ready: false, stage: 'hydrating' };
  }
  if (!store.getState().incognitoMode) {
    store.getState().setIncognitoMode(true);
    return { ready: false, stage: 'switching' };
  }
  const notice = doc.querySelector('[data-testid="incognito-notice"]');
  if (!notice) {
    const state = store.getState();
    return {
      ready: false,
      stage: 'rendering',
      path: win.location.pathname,
      chatId: state.chatId,
      messages: state.messages.length,
      headline: doc.querySelector('h2')?.textContent ?? null,
      hasTextarea: !!doc.querySelector('textarea'),
      testIds: Array.from(doc.querySelectorAll('[data-testid]')).slice(0, 12).map((el) => el.getAttribute('data-testid')),
    };
  }
  const box = notice.getBoundingClientRect();
  const root = doc.documentElement;
  return {
    ready: true,
    innerWidth: win.innerWidth,
    insideViewport: box.left >= 0 && box.right <= win.innerWidth,
    pageOverflowsX: root.scrollWidth > root.clientWidth,
  };
})()"""

_REMOVE_PHONE_FRAME = """(() => {
  document.getElementById('e2e-phone-frame')?.remove();
  return { ready: true };
})()"""

_MIN_TEXT_CONTRAST = 4.5
# Once the page is hydrated a store change renders on the next frame; the bound only absorbs a loaded CI host.
_MAX_RENDER_LATENCY_MS = 10_000


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="READ", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_incognito_notice_follows_the_toggle_on_the_empty_chat() -> None:
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(get_e2e_api_url())

    warm_ui_route("/")
    with open_mcp_page(f"{ui_url}/", timeout_ms=90_000) as (client, page):
        dismiss_blocking_modals(client, page)
        ensure_desktop_viewport(client, page)

        off = wait_for_state(client, page, _TOGGLE_READY, timeout_sec=_warm_ui_parallel_wait_sec(120.0))
        assert off.get("pressed") == "false", off

        assert client.evaluate(page, _CLICK_TOGGLE).get("clicked") is True
        on = wait_for_state(client, page, _NOTICE_STATE, timeout_sec=30.0)
        assert on.get("latencyMs", 10**9) < _MAX_RENDER_LATENCY_MS, on
        assert on.get("textLength", 0) > 40, on
        assert on.get("insideViewport") is True, on
        assert on.get("pageOverflowsX") is False, on

        for theme in ("light", "dark"):
            measured = wait_for_state(client, page, _CONTRAST_JS.replace("__THEME__", theme), timeout_sec=30.0)
            assert measured["title"]["ratio"] >= _MIN_TEXT_CONTRAST, measured
            assert measured["body"]["ratio"] >= _MIN_TEXT_CONTRAST, measured

        phone = wait_for_state(client, page, _PHONE_FRAME_STATE, timeout_sec=_warm_ui_parallel_wait_sec(240.0))
        assert phone.get("innerWidth") == _PHONE_FRAME_WIDTH, phone
        assert phone.get("insideViewport") is True, phone
        assert phone.get("pageOverflowsX") is False, phone
        client.evaluate(page, _REMOVE_PHONE_FRAME)

        assert client.evaluate(page, _CLICK_TOGGLE).get("clicked") is True
        wait_for_state(client, page, _NOTICE_GONE, timeout_sec=30.0)
