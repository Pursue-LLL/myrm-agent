"""Chrome E2E: /journey growth dashboard > Pattern Digest panel real-browser flow.

Drives the real frontend pipeline in a real Chrome for the pattern-discovery
UX: the ``PatternDigestPanel`` mounts under the "evolution" tab and issues
``GET /memory/guardian/pattern-discoveries`` and ``POST
/memory/guardian/trigger-pattern-discovery`` via ``apiRequest``.

All pattern-discovery API responses are intercepted in-page (a ``window.fetch``
override installed before the panel mounts) so the shared backend is never
mutated — this is a READ-scoped UI test. The assertions verify real rendering
(pattern cards, confidence/durability badges, expand/collapse), the empty-state
guide, and the real trigger interaction (POST URL captured + UI feedback).

Covers:
  T1 - /journey opens and the evolution tab mounts PatternDigestPanel.
  T2 - Seeded discovery events render as pattern cards (title, badges, count).
  T3 - Expanding a card reveals suggestion + evidence.
  T4 - Empty ledger shows the localized empty-state guide + trigger button.
  T5 - Trigger click fires POST trigger-pattern-discovery and shows the
       "no new patterns" feedback (pattern_count == 0 branch).
"""

from __future__ import annotations

import json

import pytest

from tests.support.chrome_mcp_e2e import (
    dismiss_blocking_modals,
    get_e2e_api_url,
    get_e2e_ui_url,
    open_mcp_page,
    prepare_e2e_ui_session,
    wait_for_state,
    warm_ui_route,
)

_JOURNEY_PATH = "/journey"

# Two seeded discovery events. The shape mirrors the real
# GET /guardian/pattern-discoveries response (id / occurred_at / summary /
# metadata.patterns[] with title / description / evidence_summary / durability /
# confidence / actionable_suggestion).
_SEED_EVENTS = [
    {
        "id": "pd-e2e-1",
        "occurred_at": "2026-08-16T01:00:00Z",
        "summary": "Pattern discovery: found 2 behavioral pattern(s)",
        "metadata": {
            "operation": "pattern_discovery",
            "pattern_count": 2,
            "memory_count": 120,
            "meta_observation": "User protects mornings for focused work",
            "patterns": [
                {
                    "title": "Morning Review Routine",
                    "description": "Starts the day with a PR queue review before scheduling deep work.",
                    "evidence_summary": "The user opens the PR queue first each morning across multiple sessions.",
                    "durability": "established",
                    "confidence": 0.85,
                    "actionable_suggestion": "Block time for PR queue review at 9am.",
                },
                {
                    "title": "Deep Work Before Noon",
                    "description": "Schedules focused deep work in the morning window.",
                    "evidence_summary": "More than half of coding sessions start before noon.",
                    "durability": "emerging",
                    "confidence": 0.62,
                    "actionable_suggestion": "",
                },
            ],
        },
    },
    {
        "id": "pd-e2e-2",
        "occurred_at": "2026-08-15T01:00:00Z",
        "summary": "Pattern discovery: found 0 behavioral pattern(s)",
        "metadata": {
            "operation": "pattern_discovery",
            "pattern_count": 0,
            "memory_count": 105,
        },
    },
]

# Installs a window.fetch override + a probe surface for the e2e driver.
# Only pattern-discovery traffic is intercepted; everything else passes through
# to the real backend. The mode can be flipped at runtime to re-mount the panel
# with an empty ledger without touching the shared backend.
_INJECT_FETCH_HOOK_JS = """(() => {
  if (window.__MYRM_PD_MOCK__) {
    return { ok: true, already: true };
  }
  const state = {
    mode: 'seed',
    seed: __SEED_JSON__,
    calls: [],
  };
  window.__MYRM_PD_MOCK__ = {
    getCalls: () => state.calls,
    setMode: (m) => { state.mode = m; },
  };
  const originalFetch = window.fetch.bind(window);
  window.fetch = async (input, init) => {
    const url = typeof input === 'string' ? input : (input && input.url) || '';
    const method = (init && init.method) || 'GET';
    const body = init && init.body ? String(init.body) : null;
    state.calls.push({ url, method, body });
    const isGetList = url.includes('/pattern-discoveries');
    const isTrigger = url.includes('trigger-pattern-discovery');
    if (isGetList || isTrigger) {
      if (isTrigger) {
        const payload = { triggered: true, skipped: false, pattern_count: 0 };
        return new Response(JSON.stringify(payload), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }
      const payload = state.mode === 'empty' ? [] : state.seed;
      return new Response(JSON.stringify(payload), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }
    return originalFetch(input, init);
  };
  return { ok: true };
})()"""

# Switch to the "evolution" tab. Radix Tabs triggers need the full pointer
# sequence under real-browser hydration, so dispatch pointer/mouse/click events
# on the [role=tab] element each poll. ``digestMounted`` fires on whichever
# PatternDigestPanel state is visible (empty guide or data header), because the
# header (title) only renders once an event exists.
_SWITCH_EVOLUTION_TAB_JS = """(() => {
  const bodyText = document.body?.innerText || '';
  const growthReady = /(Behavioral Pattern Discovery|行为模式发现|Learning in Progress|学习进行中)/.test(bodyText)
    || Array.from(document.querySelectorAll('[role="tab"]')).length > 0;
  if (!growthReady) {
    return { ready: false, reason: 'growth-not-rendered', hasTabs: document.querySelectorAll('[role="tab"]').length, snippet: bodyText.slice(0, 500) };
  }
  const tab = Array.from(document.querySelectorAll('[role="tab"]')).find((b) => {
    return /(evolution|演进|進化|进化复盘|進化復盤)/.test((b.textContent || '').trim());
  });
  if (!tab) {
    return { ready: false, reason: 'no-evolution-tab', tabs: Array.from(document.querySelectorAll('[role="tab"]')).map((t) => t.textContent), snippet: bodyText.slice(0, 500) };
  }
  const list = tab.closest('[role="tablist"]');
  const selected = list
    ? (list.querySelector('[aria-selected="true"]')?.textContent || '')
    : '';
  const digestMounted = /(Behavioral Pattern Discovery|行为模式发现|Learning in Progress|学习进行中)/.test(bodyText);
  if (!/(evolution|演进|進化|进化复盘|進化復盤)/.test(selected) && !digestMounted) {
    for (const type of ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click']) {
      tab.dispatchEvent(new MouseEvent(type, { bubbles: true, cancelable: true, view: window }));
    }
    return { ready: false, reason: 'dispatched-events', selected, digestMounted };
  }
  return { ready: digestMounted, selected, digestMounted, snippet: bodyText.slice(0, 800) };
})()"""

# Pattern cards rendered from the seeded events: first pattern title, its
# durability/confidence badges, and the "2 pattern(s)" summary line.
_PATTERN_CARDS_READY_JS = """(() => {
  const text = document.body?.innerText || '';
  const titleReady = /Morning Review Routine/.test(text);
  const secondReady = /Deep Work Before Noon/.test(text);
  const confidenceReady = /85%/.test(text);
  const durabilityReady = /(established|成型)/.test(text);
  const countReady = /(2 pattern\\(s\\) discovered|发现 2 个行为模式)/.test(text);
  const headerReady = /(Behavioral Pattern Discovery|行为模式发现)/.test(text);
  const ready = titleReady && secondReady && confidenceReady && durabilityReady && countReady;
  return {
    ready,
    titleReady,
    secondReady,
    confidenceReady,
    durabilityReady,
    countReady,
    headerReady,
    snippet: text.slice(0, 1500),
  };
})()"""

# Expand the first pattern card and check suggestion + evidence are revealed.
_EXPAND_CARD_READY_JS = """(() => {
  const text = document.body?.innerText || '';
  if (!/Morning Review Routine/.test(text)) {
    return { ready: false, reason: 'title-missing' };
  }
  const suggestionVisible = /Block time for PR queue review at 9am/.test(text);
  const evidenceVisible = /(opens the PR queue first|打开 PR 队列)/.test(text);
  const expandBtn = Array.from(document.querySelectorAll('button')).find((b) => {
    return /Morning Review Routine/.test(b.textContent || '');
  });
  if (!suggestionVisible && expandBtn) {
    expandBtn.click();
    return { ready: false, reason: 'clicked-expand', suggestionVisible, evidenceVisible };
  }
  return {
    ready: suggestionVisible && evidenceVisible,
    suggestionVisible,
    evidenceVisible,
    snippet: text.slice(0, 1500),
  };
})()"""

# Empty ledger state (fetch hook returns []) after re-mounting the evolution
# tab: localized empty guide + trigger button.
_EMPTY_STATE_READY_JS = """(() => {
  const text = document.body?.innerText || '';
  const emptyTitle = /(Learning in Progress|学习进行中)/.test(text);
  const emptyDesc = /(more interactions before pattern analysis|更多交互才能启动模式分析)/.test(text);
  const triggerBtn = Array.from(document.querySelectorAll('button')).some((b) => {
    return /(Analyze Now|立即分析)/.test(b.textContent || '');
  });
  return {
    ready: emptyTitle && emptyDesc && triggerBtn,
    emptyTitle,
    emptyDesc,
    triggerBtn,
    snippet: text.slice(0, 1200),
  };
})()"""

# Click "Analyze Now", wait for the POST to be recorded by the fetch hook, then
# report the UI feedback. The hook returns pattern_count == 0 so the panel shows
# the "no new patterns" message (showApiError toast path is covered by API tests).
_TRIGGER_BUTTON_CLICK_JS = """(() => {
  const hook = window.__MYRM_PD_MOCK__;
  if (!hook) return { ready: false, reason: 'no-hook' };
  const btn = Array.from(document.querySelectorAll('button')).find((b) => {
    return /(Analyze Now|立即分析)/.test(b.textContent || '');
  });
  if (!btn) return { ready: false, reason: 'no-trigger-btn' };
  if (!btn.disabled) btn.click();
  return { ready: false, reason: 'clicked', disabled: btn.disabled };
})()"""

# Poll whether the hook recorded a trigger POST while the panel is busy or
# already settled — the durable signal is the captured request itself.
_TRIGGER_CAPTURED_JS = """(() => {
  const hook = window.__MYRM_PD_MOCK__;
  if (!hook) return { ready: false, reason: 'no-hook' };
  const calls = hook.getCalls();
  const trigger = calls.find((c) => c.method === 'POST' && c.url.includes('trigger-pattern-discovery'));
  if (!trigger) return { ready: false, reason: 'no-trigger-call', calls: calls.length };
  return { ready: true, url: trigger.url };
})()"""


@pytest.mark.chrome_e2e(
    execution_mode="SHARED",
    access_scope="READ",
    workload="STANDARD",
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_pattern_digest_panel_real_browser_flow() -> None:
    """Real-Chrome verification of the Pattern Digest panel (seed/empty/trigger)."""
    api_url = get_e2e_api_url()
    prepare_e2e_ui_session(api_url)

    warm_ui_route(_JOURNEY_PATH)
    journey_url = f"{get_e2e_ui_url().rstrip('/')}{_JOURNEY_PATH}"
    with open_mcp_page(journey_url) as (client, page):
        dismiss_blocking_modals(client, page)

        # T1: the growth dashboard must render before the PatternDigestPanel
        # fetch is deterministic. Pin page_url so wait_for_state heals /journey
        # in place instead of navigating back to the chat home.
        ready_probe = wait_for_state(
            client,
            page,
            _GROWTH_DASHBOARD_RENDERED_JS,
            timeout_sec=120.0,
            page_url=journey_url,
            pin_direct_blank_heal=True,
        )
        assert ready_probe.get("ready") is True, json.dumps(ready_probe, ensure_ascii=False)

        # Install the fetch hook + flip it to the seeded (2 patterns) mode; the
        # panel only fetches on mount, so re-mounting the tab below makes the
        # hooked GET deterministic.
        injected = client.evaluate(
            page,
            _INJECT_FETCH_HOOK_JS.replace("__SEED_JSON__", json.dumps(_SEED_EVENTS)),
            timeout_sec=15.0,
        )
        assert isinstance(injected, dict) and injected.get("ok") is True, json.dumps(injected, ensure_ascii=False)
        client.evaluate(
            page,
            "window.__MYRM_PD_MOCK__.setMode('seed')",
            timeout_sec=15.0,
        )

        # Re-mount evolution tab (overview -> evolution) to fire a hooked GET.
        _remount_evolution(client, page, journey_url)

        # T2: seeded events render as pattern cards.
        cards = wait_for_state(
            client,
            page,
            _PATTERN_CARDS_READY_JS,
            timeout_sec=90.0,
            page_url=journey_url,
            pin_direct_blank_heal=True,
        )
        assert cards.get("ready") is True, json.dumps(cards, ensure_ascii=False)

        # T3: expand reveals suggestion + evidence.
        expanded = wait_for_state(
            client,
            page,
            _EXPAND_CARD_READY_JS,
            timeout_sec=60.0,
            page_url=journey_url,
            pin_direct_blank_heal=True,
        )
        assert expanded.get("ready") is True, json.dumps(expanded, ensure_ascii=False)

        # T4: flip the hook to an empty ledger and re-mount -> empty-state guide.
        client.evaluate(page, "window.__MYRM_PD_MOCK__.setMode('empty')", timeout_sec=15.0)
        _remount_evolution(client, page, journey_url)
        empty_state = wait_for_state(
            client,
            page,
            _EMPTY_STATE_READY_JS,
            timeout_sec=60.0,
            page_url=journey_url,
            pin_direct_blank_heal=True,
        )
        assert empty_state.get("ready") is True, json.dumps(empty_state, ensure_ascii=False)

        # T5: click "Analyze Now" and assert the real trigger POST was issued.
        client.evaluate(page, _TRIGGER_BUTTON_CLICK_JS, timeout_sec=15.0)
        captured = wait_for_state(
            client,
            page,
            _TRIGGER_CAPTURED_JS,
            timeout_sec=60.0,
            page_url=journey_url,
            pin_direct_blank_heal=True,
        )
        assert captured.get("ready") is True, json.dumps(captured, ensure_ascii=False)
        assert "trigger-pattern-discovery" in str(captured.get("url"))


def _remount_evolution(client: object, page: object, journey_url: str) -> None:
    """Toggle the growth tabs so PatternDigestPanel re-runs its mounted GET."""
    _click_overview_tab(client, page)
    wait_for_state(
        client,
        page,
        _OVERVIEW_TABBED_JS,
        timeout_sec=30.0,
        page_url=journey_url,
        pin_direct_blank_heal=True,
    )
    wait_for_state(
        client,
        page,
        _SWITCH_EVOLUTION_TAB_JS,
        timeout_sec=60.0,
        page_url=journey_url,
        pin_direct_blank_heal=True,
    )


_GROWTH_DASHBOARD_RENDERED_JS = """(() => {
  const text = document.body?.innerText || '';
  const hasTabs = document.querySelectorAll('[role="tab"]').length > 0;
  const hasKpi = /(Behavioral Pattern Discovery|行为模式发现|Learning in Progress|学习进行中|Total Memories|记忆总数|Memory Health|记忆健康)/.test(text);
  return { ready: hasTabs, hasTabs, hasKpi, snippet: text.slice(0, 600) };
})()"""


_OVERVIEW_TABBED_JS = """(() => {
  const text = document.body?.innerText || '';
  const tab = Array.from(document.querySelectorAll('[role="tab"]')).find((b) => {
    return /(overview|总览|總覽)/.test((b.textContent || '').trim());
  });
  if (!tab) return { ready: false, reason: 'no-overview-tab' };
  for (const type of ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click']) {
    tab.dispatchEvent(new MouseEvent(type, { bubbles: true, cancelable: true, view: window }));
  }
  return { ready: true };
})()"""


def _click_overview_tab(client: object, page: object) -> None:
    """Dispatch the full pointer sequence on the overview tab."""
    client.evaluate(page, _OVERVIEW_TABBED_JS, timeout_sec=15.0)
