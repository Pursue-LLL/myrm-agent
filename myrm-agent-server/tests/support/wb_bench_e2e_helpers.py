"""Shared Chrome E2E probes and helpers for the WorkBuddy Bench Eval Lab UI.

Both WBBench E2E files used to duplicate the Radix-Tabs activation trick, the
sources probe and the route-restore logic. Centralizing them here keeps the
original scenarios and any new ones (extra subset downloads, refresh-after-
download, disabled buttons) in lockstep.

Radix Tabs selects on pointerdown/mousedown, not the ``click`` event — every
interaction dispatches the full pointer→mouse sequence. Probes are wrapped in
IIFEs because ``wait_for_state`` re-evaluates the same script in one global
scope on each poll; a top-level ``const`` would collide on the second poll.

The four subset cards share a wrapping grid container whose ``textContent``
contains every ``WBBench <track>`` name, so naive ancestor matching cannot tell
which card a button belongs to. Every probe therefore resolves the *card scope*
first: the closest ancestor whose text content contains the target track name
and none of the other three.
"""

from __future__ import annotations

import shutil
from pathlib import Path

EVAL_LAB_PATH = "/eval-lab"

# The shared backend resolves ".myrm/wb_bench" against the server working
# directory; this helper runs from the same repo checkout, so the server root is
# two levels above tests/support (server/tests/support -> server).
_SERVER_ROOT = Path(__file__).resolve().parents[2]


def reset_wb_bench_source(archive_stem: str) -> None:
    """Remove an installed WBBench source so a real download flow can run again.

    Deletes only the extracted source under sources/ (the cached archive under
    archives/ is kept, so re-downloading reuses the tarball instead of hitting
    HuggingFace again). No-op when the source is not installed.
    """
    target = _SERVER_ROOT / ".myrm/wb_bench/sources" / archive_stem
    if (target / "tasks").is_dir():
        shutil.rmtree(target)


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

# Resolves the DOM node that belongs to exactly one subset: the closest ancestor
# of any button whose text content includes the target track name and excludes
# the other three tracks.
_CARD_RESOLVER_JS = """function resolveCard(name) {
  const names = ['WBBench Code', 'WBBench Web', 'WBBench Office', 'WBBench Security'];
  const others = names.filter((n) => n !== name);
  for (const btn of Array.from(document.querySelectorAll('button'))) {
    let node = btn.parentElement;
    while (node && node !== document.body) {
      const text = node.textContent || '';
      if (text.includes(name) && others.every((n) => !text.includes(n))) {
        return { card: node, buttons: Array.from(node.querySelectorAll('button')) };
      }
      node = node.parentElement;
    }
  }
  return null;
}
"""

# Verifies the four subset cards plus per-card task counts and download buttons
# rendered from the live API. The WBBench cards live under the "sources" tab
# (default tab is the case editor), so the probe first activates that tab.
# Counts and buttons are checked per card scope so unrelated page numbers
# (e.g. home stats) cannot satisfy the probe.
SOURCES_READY_JS = (
    _ACTIVATE_SOURCES_TAB_JS
    + "(() => {\n"
    + _CARD_RESOLVER_JS
    + """  // innerText reads '' while the E2E Chrome window is backgrounded; fall back to
  // textContent so the probe works regardless of window visibility.
  const body = document.body?.innerText || document.body?.textContent || '';
  const names = ['WBBench Code', 'WBBench Web', 'WBBench Office', 'WBBench Security'];
  const present = names.map((n) => body.includes(n));
  const cardState = names.map((name) => {
    const scope = resolveCard(name);
    if (!scope) return { name, hasBtn: false, hasNumber: false, cards: 0 };
    const downloadBtn = scope.buttons.find((b) => /Download|下载/.test(b.textContent || ''));
    return {
      name,
      hasBtn: !!downloadBtn,
      hasNumber: /\\b\\d+\\b/.test(scope.card.textContent || ''),
      cards: scope.buttons.length,
    };
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

    Re-activates the sources tab in case a navigation reset the tab state, then
    resolves the card scope for the subset before locating its download button.
    """
    return (
        _ACTIVATE_SOURCES_TAB_JS
        + "(() => {\n"
        + _CARD_RESOLVER_JS
        + f"""  const scope = resolveCard({subset_name!r});
  if (!scope) return {{ ok: false, err: 'card-not-found', subset: {subset_name!r} }};
  const target = scope.buttons.find((b) => /Download|下载/.test(b.textContent || ''));
  if (!target) return {{ ok: false, err: 'download-button-missing' }};
  if (target.disabled) {{
    const body = document.body?.innerText || document.body?.textContent || '';
    return {{
      ok: false,
      err: 'download-button-disabled',
      btnText: (target.textContent || '').trim().slice(0, 30),
      bodySnippet: body.slice(0, 300),
      runningIndicator: /running|运行中|评估中|evaluating|downloading|下载中/i.test(body),
    }};
  }}
  const opts = {{ bubbles: true, cancelable: true, view: window, button: 0, buttons: 1, detail: 1 }};
  target.dispatchEvent(new PointerEvent('pointerdown', opts));
  target.dispatchEvent(new MouseEvent('mousedown', opts));
  target.dispatchEvent(new PointerEvent('pointerup', opts));
  target.dispatchEvent(new MouseEvent('mouseup', opts));
  target.dispatchEvent(new MouseEvent('click', opts));
  return {{ ok: true, clicked: true }};
}})()"""
    )


def click_subset_run_js(subset_name: str) -> str:
    """Return a probe that clicks the Run button inside one subset card."""
    return (
        _ACTIVATE_SOURCES_TAB_JS
        + "(() => {\n"
        + _CARD_RESOLVER_JS
        + f"""  const scope = resolveCard({subset_name!r});
  if (!scope) return {{ ok: false, err: 'card-not-found', subset: {subset_name!r} }};
  const target = scope.buttons.find((b) => /Run|运行/i.test(b.textContent || ''));
  if (!target) return {{ ok: false, err: 'run-button-missing' }};
  if (target.disabled) return {{ ok: false, err: 'run-button-disabled' }};
  const opts = {{ bubbles: true, cancelable: true, view: window, button: 0, buttons: 1, detail: 1 }};
  target.dispatchEvent(new PointerEvent('pointerdown', opts));
  target.dispatchEvent(new MouseEvent('mousedown', opts));
  target.dispatchEvent(new PointerEvent('pointerup', opts));
  target.dispatchEvent(new MouseEvent('mouseup', opts));
  target.dispatchEvent(new MouseEvent('click', opts));
  return {{ ok: true, clicked: true }};
}})()"""
    )


def all_cards_memory_ab_ready_js() -> str:
    """Probe that every subset card exposes a working Memory A/B button.

    Re-uses the same card resolver as SOURCES_READY_JS so the four cards are
    scoped individually; returns per-card states for actionable failures.
    """
    return (
        _ACTIVATE_SOURCES_TAB_JS
        + "(() => {\n"
        + _CARD_RESOLVER_JS
        + """  const names = ['WBBench Code', 'WBBench Web', 'WBBench Office', 'WBBench Security'];
  const states = names.map((name) => {
    const scope = resolveCard(name);
    if (!scope) return { name, found: false, hasMemoryAb: false };
    const btn = scope.buttons.find((b) => /Memory A\\/B|记忆 A\\/B/i.test(b.textContent || ''));
    return { name, found: true, hasMemoryAb: !!btn, disabled: btn ? btn.disabled : null };
  });
  const allFound = states.every((s) => s.found && s.hasMemoryAb);
  return { ready: allFound, states };
})()"""
    )


def click_subset_memory_ab_js(subset_name: str) -> str:
    """Return a probe that clicks the Memory A/B button inside one subset card.

    Only opens the confirmation dialog; the run itself starts when the dialog's
    Start Evaluation button is clicked by a separate probe.
    """
    return (
        _ACTIVATE_SOURCES_TAB_JS
        + "(() => {\n"
        + _CARD_RESOLVER_JS
        + f"""  const scope = resolveCard({subset_name!r});
  if (!scope) return {{ ok: false, err: 'card-not-found', subset: {subset_name!r} }};
  const target = scope.buttons.find((b) => /Memory A\\/B|记忆 A\\/B/i.test(b.textContent || ''));
  if (!target) return {{ ok: false, err: 'memory-ab-button-missing' }};
  if (target.disabled) return {{ ok: false, err: 'memory-ab-button-disabled' }};
  const opts = {{ bubbles: true, cancelable: true, view: window, button: 0, buttons: 1, detail: 1 }};
  target.dispatchEvent(new PointerEvent('pointerdown', opts));
  target.dispatchEvent(new MouseEvent('mousedown', opts));
  target.dispatchEvent(new PointerEvent('pointerup', opts));
  target.dispatchEvent(new MouseEvent('mouseup', opts));
  target.dispatchEvent(new MouseEvent('click', opts));
  return {{ ok: true, clicked: true }};
}})()"""
    )


def all_grid_buttons_disabled_js() -> str:
    """Probe that every Download/Run button across all four cards is disabled.

    Used while a download/run is in flight: the backend marks eval busy and the
    frontend disables every action button on the sources grid.
    """
    return (
        _ACTIVATE_SOURCES_TAB_JS
        + "(() => {\n"
        + _CARD_RESOLVER_JS
        + """  const names = ['WBBench Code', 'WBBench Web', 'WBBench Office', 'WBBench Security'];
  const states = names.map((name) => {
    const scope = resolveCard(name);
    if (!scope) return { name, found: false, total: 0, disabledCount: 0 };
    const actionBtns = scope.buttons.filter((b) => /Download|下载|Run|运行/i.test(b.textContent || ''));
    return {
      name,
      found: true,
      total: actionBtns.length,
      disabledCount: actionBtns.filter((b) => b.disabled === true).length,
    };
  });
  const allFound = states.every((s) => s.found && s.total >= 2);
  const allDisabled = states.every((s) => s.total > 0 && s.total === s.disabledCount);
  return { ready: allFound && allDisabled, states };
})()"""
    )


def click_refresh_js() -> str:
    """Probe that clicks the manual Refresh button on the sources heading."""
    return (
        _ACTIVATE_SOURCES_TAB_JS
        + """(() => {
  const target = Array.from(document.querySelectorAll('button')).find((b) => {
    const text = (b.textContent || '').trim();
    return /Refresh|刷新/i.test(text);
  });
  if (!target) return { ok: false, err: 'refresh-button-missing' };
  const opts = { bubbles: true, cancelable: true, view: window, button: 0, buttons: 1, detail: 1 };
  target.dispatchEvent(new PointerEvent('pointerdown', opts));
  target.dispatchEvent(new MouseEvent('mousedown', opts));
  target.dispatchEvent(new PointerEvent('pointerup', opts));
  target.dispatchEvent(new MouseEvent('mouseup', opts));
  target.dispatchEvent(new MouseEvent('click', opts));
  return { ok: true, clicked: true };
})()"""
    )


def subset_downloaded_js(subset_name: str) -> str:
    """Wait for one subset card to show the downloaded state (badge + disabled button)."""
    return (
        _ACTIVATE_SOURCES_TAB_JS
        + "(() => {\n"
        + _CARD_RESOLVER_JS
        + f"""  const body = document.body?.innerText || document.body?.textContent || '';
  const scope = resolveCard({subset_name!r});
  if (!scope) return {{ ready: false, found: false, bodyLength: body.length }};
  const target = scope.buttons.find((b) => /Downloaded|已下载/i.test(b.textContent || ''));
  return {{
    ready: !!target && target.disabled === true,
    found: !!target,
    disabled: target ? target.disabled : null,
    btnText: target ? (target.textContent || '').trim().slice(0, 30) : null,
    bodyLength: body.length,
  }};
}})()"""
    )
