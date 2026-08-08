"""Shared Chrome E2E probes and helpers for the WorkBuddy Bench Eval Lab UI.

Both WBBench E2E files used to duplicate the Radix-Tabs activation trick, the
sources probe and the route-restore logic. Centralizing them here keeps the
original scenarios and any new ones (extra subset downloads, refresh-after-
download, disabled buttons) in lockstep.

Radix Tabs selects on pointerdown/mousedown, not the ``click`` event — every
interaction dispatches the full pointer→mouse sequence. Probes are wrapped in
IIFEs because ``wait_for_state`` re-evaluates the same script in one global
scope on each poll; a top-level ``const`` would collide on the second poll.
"""

from __future__ import annotations

EVAL_LAB_PATH = "/eval-lab"

_PATH_PROBE_JS = "(() => ({ path: location.pathname }))()"

# Names rendered by the WBBench cards (from wb_bench.list_wb_bench_sources).
_SUBSET_NAMES: tuple[str, ...] = (
    "WBBench Code",
    "WBBench Web",
    "WBBench Office",
    "WBBench Security",
)

_ACTIVATE_SOURCES_TAB_JS = """(() => {
  const tab = Array.from(document.querySelectorAll('[role="tab"]')).find(
    (b) => /Dataset Sources|数据集源|データセットソース/i.test(b.textContent || ''),
  );
  if (!tab || tab.getAttribute('data-state') === 'active') return;
  const opts = { bubbles: true, cancelable: true, view: window, button: 0, buttons: 1, detail: 1 };
  tab.dispatchEvent(new PointerEvent('pointerdown', opts));
  tab.dispatchEvent(new MouseEvent('mousedown', opts));
  tab.dispatchEvent(new PointerEvent('pointerup', opts));
  tab.dispatchEvent(new MouseEvent('mouseup', opts));
  tab.dispatchEvent(new MouseEvent('click', opts));
})();
"""

# Verifies the four subset cards plus per-card task counts and download buttons
# rendered from the live API. The WBBench cards live under the "sources" tab
# (default tab is the case editor), so the probe first activates that tab.
# Counts and buttons are checked per card container so unrelated page numbers
# (e.g. home stats) cannot satisfy the probe.
SOURCES_READY_JS = (
    _ACTIVATE_SOURCES_TAB_JS
    + """(() => {
  // innerText reads '' while the E2E Chrome window is backgrounded; fall back to
  // textContent so the probe works regardless of window visibility.
  const body = document.body?.innerText || document.body?.textContent || '';
  const names = ['WBBench Code', 'WBBench Web', 'WBBench Office', 'WBBench Security'];
  const present = names.map((n) => body.includes(n));
  const cardState = names.map((name) => {
    const btn = Array.from(document.querySelectorAll('button')).find((b) => {
      if (!/Download|下载/i.test(b.textContent || '')) return false;
      let node = b.parentElement;
      while (node && node !== document.body) {
        if ((node.textContent || '').includes(name)) return true;
        node = node.parentElement;
      }
      return false;
    });
    if (!btn) return { name, hasBtn: false, hasNumber: false };
    let card = btn.parentElement;
    while (card && card !== document.body && !(card.textContent || '').includes(name)) {
      card = card.parentElement;
    }
    const text = card?.textContent || '';
    return { name, hasBtn: true, hasNumber: /\\b\\d+\\b/.test(text) };
  });
  const allPresent = present.every(Boolean);
  const allCardsOk = cardState.every((c) => c.hasBtn && c.hasNumber);
  return {
    ready: allPresent && allCardsOk,
    present,
    cardState,
    downloadButtons: cardState.filter((c) => c.hasBtn).length,
    path: location.pathname,
    bodyLength: body.length,
  };
})()"""
)

# Re-assert the eval-lab route after the shared UI session contract. The
# contract's BRIDGE phase reloads the page to the UI root when the E2E Chrome
# window is backgrounded (innerText reads empty), which would drop /eval-lab
# from the URL. Navigate back so the probe polls the right page.
def restore_eval_lab_route(
    client: object,
    page: object,
    target_url: str,
) -> None:
    raw = client.evaluate(page, _PATH_PROBE_JS, timeout_sec=15.0)
    current = str(raw.get("path") or "").rstrip("/") if isinstance(raw, dict) else ""
    if current != EVAL_LAB_PATH:
        client.navigate(page, target_url, timeout_ms=90_000)


def click_subset_download_js(subset_name: str) -> str:
    """Return a probe that clicks the Download button inside one subset card.

    Re-activates the sources tab in case a navigation reset the tab state.
    """
    return (
        _ACTIVATE_SOURCES_TAB_JS
        + f"""(() => {{
  const buttons = Array.from(document.querySelectorAll('button'));
  const target = buttons.find((b) => {{
    if (!/Download|下载/i.test(b.textContent || '')) return false;
    let node = b.parentElement;
    while (node && node !== document.body) {{
      if ((node.textContent || '').includes({subset_name!r})) return true;
      node = node.parentElement;
    }}
    return false;
  }});
  if (!target) return {{ ok: false, err: 'download-button-missing' }};
  if (target.disabled) return {{ ok: false, err: 'download-button-disabled' }};
  const opts = {{ bubbles: true, cancelable: true, view: window, button: 0, buttons: 1, detail: 1 }};
  target.dispatchEvent(new PointerEvent('pointerdown', opts));
  target.dispatchEvent(new MouseEvent('mousedown', opts));
  target.dispatchEvent(new PointerEvent('pointerup', opts));
  target.dispatchEvent(new MouseEvent('mouseup', opts));
  target.dispatchEvent(new MouseEvent('click', opts));
  return {{ ok: true, clicked: true }};
}})()"""
    )


def subset_downloaded_js(subset_name: str) -> str:
    """Wait for one subset card to show the downloaded state (badge + disabled button)."""
    return (
        _ACTIVATE_SOURCES_TAB_JS
        + f"""(() => {{
  const body = document.body?.innerText || document.body?.textContent || '';
  const buttons = Array.from(document.querySelectorAll('button'));
  const target = buttons.find((b) => {{
    if (!/Downloaded|已下载/i.test(b.textContent || '')) return false;
    let node = b.parentElement;
    while (node && node !== document.body) {{
      if ((node.textContent || '').includes({subset_name!r})) return true;
      node = node.parentElement;
    }}
    return false;
  }});
  return {{
    ready: !!target && target.disabled === true,
    found: !!target,
    disabled: target ? target.disabled : null,
    bodyLength: body.length,
  }};
}})()"""
    )
