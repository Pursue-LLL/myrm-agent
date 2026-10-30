"""Chrome E2E: the nav rail's tools menu is a readable popover and each entry opens the panel it names.

Five floating HUD capsules were folded into one nav-rail entry. The unit tests mock Radix, so only a real browser shows
that the popover sits inside the viewport, is not covered by the phone drawer, stays readable in both themes, and that
every entry reaches its panel. The menu is client state only, so the lane is SHARED+READ.

The app runs in a fixed-size same-origin frame: ``window.resizeTo`` is a no-op in this Chrome and the layout switches to
the phone shell below 1024px, so only a frame pins the shell under test. Labels and panel titles come from the shipped
locale files, so the test follows the copy instead of restating it.

Formal run::

    ./myrm-dev test -m chrome_e2e \\
      myrm-agent/myrm-agent-server/tests/e2e/test_utility_menu_chrome_e2e.py
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Literal, cast

import pytest

from tests.support.chrome_mcp_e2e import (
    ChromeMcpClient,
    McpPage,
    _warm_ui_parallel_wait_sec,
    dismiss_blocking_modals,
    get_e2e_api_url,
    get_e2e_ui_url,
    open_mcp_page,
    prepare_e2e_ui_session,
    wait_for_state,
    warm_ui_route,
)

pytestmark = [pytest.mark.integration, pytest.mark.timeout(600)]

_LOCALES_DIR = Path(__file__).resolve().parents[3] / "myrm-agent-frontend" / "locales"
_LOCALES = ("en", "zh", "zh-TW", "ja", "ko", "de")

_DESKTOP_VIEWPORT = (1280, 900)
_PHONE_VIEWPORT = (390, 844)
_MIN_TEXT_CONTRAST = 4.5


@dataclass(frozen=True)
class _Panel:
    """One menu entry and the marker of the panel it has to open."""

    name: str
    entry_label: tuple[str, str]  # (namespace, key) of the entry's label
    marker: Literal["aside", "dialog"]  # a labelled region, or an open <dialog> that carries the title
    marker_text: tuple[str, str]  # (namespace, key) of the region label or dialog title


_PANELS = (
    _Panel("workbench", ("workbench", "hudTrigger"), "aside", ("workbench", "workbenchAriaLabel")),
    _Panel("session-map", ("sessionMap", "hudTrigger"), "dialog", ("sessionMap", "modalTitle")),
    _Panel("presentation", ("presentation", "menuLabel"), "dialog", ("presentation", "modalTitle")),
    _Panel("tool-picker", ("toolPicker", "menuLabel"), "dialog", ("toolPicker", "modalTitle")),
    _Panel("assistant", ("systemAssistant", "assistantName"), "dialog", ("systemAssistant", "hubTitle")),
)


@cache
def _messages(locale: str) -> dict[str, dict[str, object]]:
    return json.loads((_LOCALES_DIR / f"{locale}.json").read_text(encoding="utf-8"))


def _labels(namespace: str, key: str) -> list[str]:
    """The string at `<namespace>.<key>` in every shipped locale, without duplicates."""
    return list(dict.fromkeys(str(_messages(locale)[namespace][key]) for locale in _LOCALES))


# Every probe runs against the app inside the frame. `findButton` matches by accessible name because the controls carry
# no test ids; the rest of the helpers are shared by the probes below.
_FRAME_PRELUDE = """
  const frame = document.getElementById('e2e-app-frame');
  const win = frame ? frame.contentWindow : null;
  const doc = win ? win.document : null;
  const isHydrated = (el) => !!el && Object.keys(el).some((key) => key.startsWith('__reactProps'));
  const findButton = (labels) =>
    Array.from(doc.querySelectorAll('button')).find((el) => labels.includes(el.getAttribute('aria-label') || ''));
  const menuContent = () => {
    const trigger = findButton(__TRIGGER__);
    const id = trigger ? trigger.getAttribute('aria-controls') : null;
    return id ? doc.getElementById(id) : null;
  };
  // Radix positions and animates the popover after mounting and the phone drawer slides in, so a rectangle that is
  // unchanged since the previous poll is one that has stopped moving.
  const settled = (slot, el) => {
    const box = el.getBoundingClientRect();
    const key = [box.left, box.top, box.width, box.height].map(Math.round).join(',');
    const unchanged = win[slot] === key;
    win[slot] = key;
    return unchanged;
  };
"""

# The phone shell renders the drawer opener only after the layout switched, so its hydration proves the shell.
_FRAME_STATE = """
  if (!frame) {
    const created = document.createElement('iframe');
    created.id = 'e2e-app-frame';
    created.style.cssText =
      'position:fixed;left:0;top:0;width:__WIDTH__px;height:__HEIGHT__px;border:0;z-index:2147483647;background:#fff';
    created.src = location.origin + '/';
    document.body.appendChild(created);
    return { ready: false, stage: 'loading' };
  }
  const trigger = findButton(__TRIGGER__);
  const opener = findButton(__OPENER__);
  const hydrated = __LAYOUT__ === 'phone' ? isHydrated(opener) : isHydrated(trigger) && !opener;
  return {
    ready: hydrated,
    stage: 'hydrating',
    innerWidth: win.innerWidth,
    hasTrigger: !!trigger,
    hasOpener: !!opener,
    path: win.location.pathname,
  };
"""

_TRIGGER_SETTLED = """
  const trigger = findButton(__TRIGGER__);
  if (!isHydrated(trigger)) {
    return { ready: false, stage: 'hydrating' };
  }
  const unchanged = settled('__e2eTrigger', trigger);
  const box = trigger.getBoundingClientRect();
  return { ready: unchanged && box.left >= 0 && box.right <= win.innerWidth, left: box.left, right: box.right };
"""

_CLICK_BUTTON = """
  const target = findButton(__LABELS__);
  if (!isHydrated(target)) {
    return { clicked: false };
  }
  target.click();
  return { clicked: true };
"""

_CLICK_ENTRY = """
  const content = menuContent();
  const entry = content
    ? Array.from(content.querySelectorAll('button')).find((el) => {
        const label = el.querySelector('span');
        return __LABELS__.includes(label ? label.textContent.trim() : '');
      })
    : null;
  if (!entry) {
    return { clicked: false };
  }
  entry.click();
  return { clicked: true };
"""

_MENU_STATE = """
  const trigger = findButton(__TRIGGER__);
  const content = menuContent();
  if (!content) {
    return { ready: false, expanded: trigger ? trigger.getAttribute('aria-expanded') : null };
  }
  const entries = Array.from(content.querySelectorAll('button'));
  const unchanged = settled('__e2eMenu', content);
  const box = content.getBoundingClientRect();
  const root = doc.documentElement;
  return {
    ready: entries.length > 0 && unchanged,
    haspopup: trigger.getAttribute('aria-haspopup'),
    expanded: trigger.getAttribute('aria-expanded'),
    role: content.getAttribute('role'),
    viewportWidth: win.innerWidth,
    insideViewport: box.left >= 0 && box.top >= 0 && box.right <= win.innerWidth && box.bottom <= win.innerHeight,
    pageOverflowsX: root.scrollWidth > root.clientWidth,
    entries: entries.map((entry) => {
      const label = entry.querySelector('span');
      const shortcut = entry.querySelector('kbd');
      const rect = entry.getBoundingClientRect();
      const hit = doc.elementFromPoint(rect.left + rect.width / 2, rect.top + rect.height / 2);
      return {
        label: label ? label.textContent.trim() : '',
        shortcut: shortcut ? shortcut.textContent.trim() : '',
        truncated: !!label && label.scrollWidth > label.clientWidth,
        reachable: !!hit && entry.contains(hit),
      };
    }),
  };
"""

# Text contrast as the user sees it: the ancestor backgrounds and the text color are composited on a canvas, which
# resolves whatever color syntax the theme variables use, then WCAG relative luminance is compared.
_CONTRAST = """
  const content = menuContent();
  if (!content) {
    return { ready: false };
  }
  if (!doc.getElementById('e2e-no-transition')) {
    // Colors are transitioned, so a measurement right after the class swap would read the previous theme.
    const style = doc.createElement('style');
    style.id = 'e2e-no-transition';
    style.textContent = '*, *::before, *::after { transition: none !important; }';
    doc.head.appendChild(style);
  }
  doc.documentElement.classList.remove('light', 'dark');
  doc.documentElement.classList.add(__THEME__);
  const ctx = doc.createElement('canvas').getContext('2d', { willReadFrequently: true });
  const paint = (css) => {
    ctx.fillStyle = css;
    ctx.fillRect(0, 0, 1, 1);
  };
  const pixel = () => Array.from(ctx.getImageData(0, 0, 1, 1).data).slice(0, 3);
  const luminance = ([r, g, b]) => {
    const [lr, lg, lb] = [r, g, b].map((v) => {
      const c = v / 255;
      return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
    });
    return 0.2126 * lr + 0.7152 * lg + 0.0722 * lb;
  };
  const contrast = (el) => {
    paint('#ffffff');
    const chain = [];
    for (let node = el; node; node = node.parentElement) {
      chain.unshift(node);
    }
    for (const node of chain) {
      paint(win.getComputedStyle(node).backgroundColor);
    }
    const background = pixel();
    paint('rgb(' + background.join(',') + ')');
    paint(win.getComputedStyle(el).color);
    const text = pixel();
    const hi = Math.max(luminance(background), luminance(text));
    const lo = Math.min(luminance(background), luminance(text));
    return { ratio: (hi + 0.05) / (lo + 0.05), text, background };
  };
  return {
    ready: true,
    theme: __THEME__,
    heading: contrast(content.querySelector('p')),
    label: contrast(content.querySelector('button span')),
    shortcut: contrast(content.querySelector('button kbd')),
  };
"""

# `dialog`: panels render a modal <dialog> that is open and carries the title (the presentation dialog stays mounted
# while closed, so `open` is what counts). `aside`: the workbench is a labelled region that only exists while open.
_PANEL_OPEN = """
  const trigger = findButton(__TRIGGER__);
  const menuClosed = !!trigger && trigger.getAttribute('aria-expanded') === 'false';
  const texts = __TEXTS__;
  const panel =
    __MARKER__ === 'aside'
      ? Array.from(doc.querySelectorAll('aside')).find((el) => texts.includes(el.getAttribute('aria-label') || ''))
      : Array.from(doc.querySelectorAll('dialog')).find(
          (el) => el.open && texts.some((text) => (el.textContent || '').includes(text)),
        );
  const box = panel ? panel.getBoundingClientRect() : null;
  return {
    ready: menuClosed && !!box && box.width > 0 && box.height > 0,
    menuClosed,
    found: !!panel,
    openDialogs: Array.from(doc.querySelectorAll('dialog[open]')).map((el) => (el.textContent || '').trim().slice(0, 40)),
  };
"""


def _probe(body: str, **values: object) -> str:
    """Wraps a probe body so it can reach the app frame, filling its `__NAME__` placeholders with JSON values."""
    values = {"trigger": _labels("nav", "tools"), **values}
    source = _FRAME_PRELUDE + body
    for name, value in values.items():
        source = source.replace(f"__{name.upper()}__", json.dumps(value))
    unfilled = re.findall(r"__[A-Z]+__", source)
    assert not unfilled, f"unfilled probe placeholders: {unfilled}"
    return f"(() => {{{source}}})()"


@contextmanager
def _app_frame(*, viewport: tuple[int, int], layout: Literal["desktop", "phone"]) -> Iterator[tuple[ChromeMcpClient, McpPage]]:
    """The app at a pinned viewport, hydrated in the given layout (the desktop rail or the phone drawer)."""
    prepare_e2e_ui_session(get_e2e_api_url())
    warm_ui_route("/")
    with open_mcp_page(f"{get_e2e_ui_url()}/", timeout_ms=90_000) as (client, page):
        dismiss_blocking_modals(client, page)
        width, height = viewport
        frame_state = _probe(_FRAME_STATE, width=width, height=height, layout=layout, opener=_labels("layout", "showSidebar"))
        # The frame is a second full app load: on a cold dev server its chunks can take minutes to hydrate.
        wait_for_state(client, page, frame_state, timeout_sec=_warm_ui_parallel_wait_sec(240.0))
        yield client, page


def _click_button(client: ChromeMcpClient, page: McpPage, labels: list[str]) -> None:
    clicked = client.evaluate(page, _probe(_CLICK_BUTTON, labels=labels))
    assert clicked.get("clicked") is True, clicked


def _open_menu(client: ChromeMcpClient, page: McpPage) -> dict[str, object]:
    wait_for_state(client, page, _probe(_TRIGGER_SETTLED), timeout_sec=30.0)
    _click_button(client, page, _labels("nav", "tools"))
    return wait_for_state(client, page, _probe(_MENU_STATE), timeout_sec=30.0)


def _assert_menu_usable(menu: dict[str, object], *, viewport_width: int) -> None:
    assert menu["viewportWidth"] == viewport_width, menu
    assert (menu["haspopup"], menu["expanded"], menu["role"]) == ("dialog", "true", "dialog"), menu
    assert menu["insideViewport"] is True, menu
    assert menu["pageOverflowsX"] is False, menu
    entries = cast(list[dict[str, object]], menu["entries"])
    assert len(entries) == len(_PANELS), menu
    for entry in entries:
        assert entry["label"] and entry["shortcut"], menu
        assert entry["truncated"] is False, menu
        assert entry["reachable"] is True, menu


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="READ", workload="STANDARD")
def test_tools_menu_is_labelled_readable_and_reachable_on_the_desktop_rail() -> None:
    with _app_frame(viewport=_DESKTOP_VIEWPORT, layout="desktop") as (client, page):
        _assert_menu_usable(_open_menu(client, page), viewport_width=_DESKTOP_VIEWPORT[0])

        popover_backgrounds: set[tuple[int, ...]] = set()
        for theme in ("light", "dark"):
            measured = wait_for_state(client, page, _probe(_CONTRAST, theme=theme), timeout_sec=30.0)
            popover_backgrounds.add(tuple(cast(dict[str, list[int]], measured["heading"])["background"]))
            for part in ("heading", "label", "shortcut"):
                ratio = cast(dict[str, float], measured[part])["ratio"]
                assert ratio >= _MIN_TEXT_CONTRAST, measured
        # Both themes must have been measured: a class swap that changed nothing would pass the contrast check twice.
        assert len(popover_backgrounds) == 2, popover_backgrounds


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="READ", workload="STANDARD")
@pytest.mark.parametrize("panel", _PANELS, ids=lambda panel: panel.name)
def test_tools_menu_entry_opens_its_panel_and_closes_the_menu(panel: _Panel) -> None:
    with _app_frame(viewport=_DESKTOP_VIEWPORT, layout="desktop") as (client, page):
        _open_menu(client, page)

        clicked = client.evaluate(page, _probe(_CLICK_ENTRY, labels=_labels(*panel.entry_label)))
        assert clicked.get("clicked") is True, clicked

        # A panel behind a lazy chunk compiles on first use in the dev server.
        panel_open = _probe(_PANEL_OPEN, marker=panel.marker, texts=_labels(*panel.marker_text))
        wait_for_state(client, page, panel_open, timeout_sec=90.0)


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="READ", workload="STANDARD")
def test_tools_menu_fits_the_phone_viewport_and_is_not_covered_by_the_drawer() -> None:
    with _app_frame(viewport=_PHONE_VIEWPORT, layout="phone") as (client, page):
        _click_button(client, page, _labels("layout", "showSidebar"))

        _assert_menu_usable(_open_menu(client, page), viewport_width=_PHONE_VIEWPORT[0])
