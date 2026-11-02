"""The background tasks panel as the leftover Chrome E2E files see it: page probes and the steps a user takes on the stop control.

[INPUT]
- tests.support.chrome_mcp_e2e (POS: page handles, script evaluation, state waits, the isolated runtime's UI and API urls)
- tests.support.marked_command_lines (POS: whether the program a finished job left is still in the process table)

[OUTPUT]
- background_tasks_panel: a page with the panel open, as a user reaches it from the navigation bar
- wait_for_leftover_hint, stop_leftover_from_panel, wait_until_leftover_gone: the user-visible steps on a row whose job left a program running
- measure_contrast, measure_narrow_panel: what the hint and the stop button look like in a theme and inside a narrow panel
- wait_api_row, wait_marker_gone: the same row and process as the API and the process table report them
- MIN_TEXT_CONTRAST: the contrast ratio small text must reach (WCAG AA)

[POS]
Shared by tests/e2e/test_background_tasks_leftover_chrome_e2e.py (seeded job) and test_background_tasks_leftover_live_chrome_e2e.py
(job started by the agent from the chat).
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager

from tests.support.chrome_mcp_e2e import (
    ChromeMcpClient,
    McpPage,
    dismiss_blocking_modals,
    get_e2e_ui_url,
    http_json,
    open_mcp_page,
    prepare_e2e_ui_session,
    wait_for_state,
    warm_ui_route,
)
from tests.support.marked_command_lines import processes_with_marker

OPEN_PANEL_JS = """(() => {
  const btn = document.querySelector('button[aria-label="Background Tasks"], button[aria-label="后台任务"]');
  if (!btn) {
    return { ready: false, clicked: false };
  }
  btn.click();
  return { ready: true, clicked: true };
})()"""

PANEL_READY_JS = """(() => {
  const text = document.body?.innerText || '';
  return { ready: /Background Tasks|后台任务/.test(text) && /Long-running tasks|耗时任务/.test(text) };
})()"""

LEFTOVER_HINT_JS = """(() => {
  window.dispatchEvent(new CustomEvent('myrm:background-tasks-changed'));
  const popover = document.querySelector('[data-radix-popper-content-wrapper]');
  const root = popover || document.body;
  const hint = root.querySelector('[data-testid="background-task-leftover-hint"]');
  const stop = root.querySelector('[data-testid="background-task-leftover-stop"]');
  return { ready: !!hint && !!stop, hint: hint?.textContent || '' };
})()"""

CLICK_LEFTOVER_STOP_JS = """(() => {
  const popover = document.querySelector('[data-radix-popper-content-wrapper]');
  const root = popover || document.body;
  const stop = root.querySelector('[data-testid="background-task-leftover-stop"]');
  if (!stop) return { clicked: false };
  stop.click();
  return { clicked: true };
})()"""

STOP_TOAST_JS = """(() => {
  const toasts = Array.from(document.querySelectorAll('[data-sonner-toast]'))
    .map((node) => node.textContent || '')
    .join(' ');
  return {
    ready: /Stopped what the task left running|已停止后台运行的程序/.test(toasts),
    failed: /Failed to stop it|停止失败/.test(toasts),
    toasts: toasts.slice(0, 300),
  };
})()"""

HINT_GONE_JS = """(() => {
  window.dispatchEvent(new CustomEvent('myrm:background-tasks-changed'));
  const popover = document.querySelector('[data-radix-popper-content-wrapper]');
  const root = popover || document.body;
  return {
    ready: !root.querySelector('[data-testid="background-task-leftover-hint"]')
      && !root.querySelector('[data-testid="background-task-leftover-stop"]'),
  };
})()"""

# Contrast of the hint text and the stop button label against what is painted behind them, per WCAG: the theme is
# switched the way next-themes does it (the class on <html>), colors are normalised through a canvas so any CSS color
# syntax (color-mix, oklab) reads back as sRGB.
THEME_CONTRAST_JS = """(async () => {
  const theme = '__THEME__';
  const root = document.documentElement;
  root.classList.remove('light', 'dark');
  root.classList.add(theme);
  root.style.colorScheme = theme;
  await new Promise((resolve) => setTimeout(resolve, 800));
  const canvas = document.createElement('canvas');
  canvas.width = 1;
  canvas.height = 1;
  const ctx = canvas.getContext('2d', { willReadFrequently: true });
  const rgba = (css) => {
    ctx.clearRect(0, 0, 1, 1);
    ctx.fillStyle = '#010203';
    ctx.fillStyle = css;
    ctx.fillRect(0, 0, 1, 1);
    const [r, g, b, a] = ctx.getImageData(0, 0, 1, 1).data;
    return { r, g, b, a: a / 255 };
  };
  const over = (top, base) => ({
    r: top.r * top.a + base.r * (1 - top.a),
    g: top.g * top.a + base.g * (1 - top.a),
    b: top.b * top.a + base.b * (1 - top.a),
  });
  const backgroundBehind = (el) => {
    const layers = [];
    for (let node = el; node; node = node.parentElement) {
      const layer = rgba(getComputedStyle(node).backgroundColor);
      if (layer.a > 0) layers.push(layer);
      if (layer.a >= 0.999) break;
    }
    return layers.reverse().reduce((base, layer) => over(layer, base), { r: 255, g: 255, b: 255 });
  };
  const luminance = ({ r, g, b }) => {
    const channel = (value) => {
      const c = value / 255;
      return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
    };
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
  };
  const contrastOf = (el) => {
    const background = backgroundBehind(el);
    const text = over(rgba(getComputedStyle(el).color), background);
    const [lighter, darker] = [luminance(text), luminance(background)].sort((x, y) => y - x);
    return { ratio: (lighter + 0.05) / (darker + 0.05), color: getComputedStyle(el).color };
  };
  const hint = document.querySelector('[data-testid="background-task-leftover-hint"]');
  const stop = document.querySelector('[data-testid="background-task-leftover-stop"]');
  if (!hint || !stop) return { ready: false };
  return { ready: true, theme, hint: contrastOf(hint), stop: contrastOf(stop) };
})()"""

# The panel is 340px wide on phones; at 300px the hint and the button row must wrap inside it instead of overflowing.
NARROW_PANEL_JS = """(async () => {
  const wrapper = document.querySelector('[data-radix-popper-content-wrapper]');
  const content = wrapper && wrapper.firstElementChild;
  const hint = document.querySelector('[data-testid="background-task-leftover-hint"]');
  const stop = document.querySelector('[data-testid="background-task-leftover-stop"]');
  if (!content || !hint || !stop) return { ready: false };
  content.style.width = '300px';
  await new Promise((resolve) => setTimeout(resolve, 500));
  const box = content.getBoundingClientRect();
  const inside = (el) => {
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && r.left >= box.left - 0.5 && r.right <= box.right + 0.5;
  };
  return {
    ready: true,
    width: box.width,
    hintInside: inside(hint),
    stopInside: inside(stop),
    overflowX: content.scrollWidth - content.clientWidth,
  };
})()"""

MIN_TEXT_CONTRAST = 4.5

_POLL_SECONDS = 0.5


def open_background_tasks_panel(client: ChromeMcpClient, page: McpPage) -> None:
    opened = wait_for_state(client, page, OPEN_PANEL_JS, timeout_sec=60.0)
    assert opened.get("clicked") is True, opened
    panel = wait_for_state(client, page, PANEL_READY_JS, timeout_sec=60.0)
    assert panel.get("ready") is True, panel


@contextmanager
def background_tasks_panel(api_base: str) -> Iterator[tuple[ChromeMcpClient, McpPage]]:
    prepare_e2e_ui_session(api_base)
    warm_ui_route("/")
    with open_mcp_page(get_e2e_ui_url(), timeout_ms=120_000) as (client, page):
        dismiss_blocking_modals(client, page)
        open_background_tasks_panel(client, page)
        yield client, page


def wait_for_leftover_hint(client: ChromeMcpClient, page: McpPage, *, timeout_sec: float = 60.0) -> None:
    row = wait_for_state(client, page, LEFTOVER_HINT_JS, timeout_sec=timeout_sec)
    assert row.get("ready") is True, row


def stop_leftover_from_panel(client: ChromeMcpClient, page: McpPage) -> None:
    """Press the stop button of the row and wait for the success toast; the tab stays open because closing it aborts the request."""
    clicked = client.evaluate(page, CLICK_LEFTOVER_STOP_JS, timeout_sec=10.0)
    assert clicked.get("clicked") is True, clicked
    toast = wait_for_state(client, page, STOP_TOAST_JS, timeout_sec=45.0)
    assert toast.get("ready") is True and toast.get("failed") is not True, toast


def wait_until_leftover_gone(client: ChromeMcpClient, page: McpPage) -> None:
    gone = wait_for_state(client, page, HINT_GONE_JS, timeout_sec=30.0)
    assert gone.get("ready") is True, gone


def measure_contrast(client: ChromeMcpClient, page: McpPage, theme: str) -> dict[str, dict[str, object]]:
    measured = client.evaluate(page, THEME_CONTRAST_JS.replace("__THEME__", theme), timeout_sec=20.0)
    assert measured.get("ready") is True, measured
    return {"hint": measured["hint"], "stop": measured["stop"]}


def measure_narrow_panel(client: ChromeMcpClient, page: McpPage) -> dict[str, object]:
    narrow = client.evaluate(page, NARROW_PANEL_JS, timeout_sec=20.0)
    assert narrow.get("ready") is True, narrow
    return narrow


def wait_api_row(api_base: str, task_id: str, *, leftover: int, timeout_sec: float = 30.0) -> dict[str, object]:
    deadline = time.monotonic() + timeout_sec
    last: dict[str, object] = {}
    while time.monotonic() < deadline:
        row = http_json("GET", f"{api_base}/api/v1/background-tasks/{task_id}")
        assert isinstance(row, dict)
        last = row
        if row.get("status") == "completed" and row.get("leftover_processes") == leftover:
            return row
        time.sleep(_POLL_SECONDS)
    raise AssertionError(f"{task_id} never reached completed with leftover_processes={leftover}; last={last!r}")


def wait_marker_gone(marker: str, *, timeout_sec: float = 15.0) -> None:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if not processes_with_marker(marker):
            return
        time.sleep(_POLL_SECONDS)
    raise AssertionError(f"processes carrying {marker} are still alive: {processes_with_marker(marker)}")
