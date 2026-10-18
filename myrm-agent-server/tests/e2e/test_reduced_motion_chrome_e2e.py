"""Chrome E2E: the WebUI ships a real reduced-motion guard that covers every animation.

Prerequisites:
  ./myrm ready --attach --chrome

Covers T1..T3 of the guard this task shipped:
  T1 - A decorative infinite animation really runs on the live page (so T2 cannot pass vacuously).
  T2 - The browser parsed the guard: `@media (prefers-reduced-motion: reduce)` exists in the
       document's own stylesheet and targets the universal selector with the expected declarations.
  T3 - The guard normalises only durations/iterations, i.e. it keeps the cascade for components
       that set their own animation (the shipped block never uses `animation: none`).

Why the preference is read from the parsed stylesheet rather than emulated: Chrome permits one
CDP client per target, and this harness's orchestrator already owns that session, so a second
connection would displace it (`Emulation.setEmulatedMedia` verifiably works on a bare target but
drops the mux session here). The CSS-collapse behaviour itself is measured in the unit suite and
in a standalone Chromium run recorded in BUGFIX_LOG -002; this test proves the rule really
reaches a real browser and is not stripped by the Tailwind build.
"""

from __future__ import annotations

import time

import pytest

from tests.support.chrome_mcp_e2e import (
    ChromeMcpClient,
    get_e2e_api_url,
    get_e2e_ui_url,
    prepare_e2e_ui_session,
    warm_ui_route,
)

# Reads, from the live document, one infinite animation plus the parsed guard rule. Everything
# comes from the browser: computed styles and CSSOM, no assumptions about the source text.
_PROBE_JS = """(() => {
  const nodes = Array.from(document.querySelectorAll('.animate-pulse'));
  const animated = nodes.find((n) => getComputedStyle(n).animationName !== 'none');
  const pulse = animated
    ? (() => {
        const cs = getComputedStyle(animated);
        return { duration: cs.animationDuration, iterations: cs.animationIterationCount };
      })()
    : null;

  // Walk every same-origin sheet and locate the reduced-motion media rule.
  let guard = null;
  for (const sheet of Array.from(document.styleSheets)) {
    let rules;
    try {
      rules = sheet.cssRules;
    } catch (err) {
      continue; // cross-origin sheet; the guard never lives there
    }
    for (const rule of Array.from(rules || [])) {
      if (rule.type !== CSSRule.MEDIA_RULE) continue;
      if (!rule.conditionText || !rule.conditionText.includes('prefers-reduced-motion')) continue;
      const inner = Array.from(rule.cssRules || []);
      // The minifier rewrites `*::after` to `:after`, so match either spelling.
      const universal = inner.find((r) => /::?after/.test(r.selectorText || ''));
      if (!universal) continue;
      guard = {
        condition: rule.conditionText,
        selector: universal.selectorText,
        animationDuration: universal.style.getPropertyValue('animation-duration'),
        iterations: universal.style.getPropertyValue('animation-iteration-count'),
        transitionDuration: universal.style.getPropertyValue('transition-duration'),
        usesAnimationNone: /animation-name\\s*:\\s*none|(?:^|;)\\s*animation\\s*:\\s*none/.test(
          universal.cssText,
        ),
      };
    }
  }
  return { pulseFound: Boolean(pulse), pulse, guard, pulseNodes: nodes.length };
})()"""


def _ms(value: str) -> float:
    """Normalise a CSS duration (`0.01ms`, `.01ms`, `2s`) to milliseconds.

    The dev-server minifier rewrites `0.01ms` as `.01ms`, so string comparison would be brittle
    while the actual value is identical.
    """
    text = str(value).strip()
    if text.endswith('ms'):
        return float(text[:-2])
    if text.endswith('s'):
        return float(text[:-1]) * 1000.0
    raise AssertionError(f'unexpected CSS duration: {value!r}')


def _probe(client: ChromeMcpClient, page) -> dict[str, object]:
    deadline = time.monotonic() + 120.0
    last: dict[str, object] = {}
    while time.monotonic() < deadline:
        result = client.evaluate(page, _PROBE_JS, timeout_sec=15.0)
        if isinstance(result, dict):
            last = result
            if last.get('pulseFound') and last.get('guard'):
                return last
        time.sleep(0.5)
    raise AssertionError(f'page never exposed both a pulse and the guard rule: {last!r}')


@pytest.mark.chrome_e2e(
    execution_mode="SHARED",
    access_scope="READ",
    workload="STANDARD",
)
@pytest.mark.integration
@pytest.mark.timeout(300)
def test_webui_ships_a_real_reduced_motion_guard() -> None:
    """The guard must reach a real browser as a parsed rule, not just exist in the source file."""
    api_url = get_e2e_api_url()
    prepare_e2e_ui_session(api_url)
    warm_ui_route('/')

    client = ChromeMcpClient()
    client.start()
    page = None
    try:
        page = client.new_page(get_e2e_ui_url(), timeout_ms=120_000)
        state = _probe(client, page)

        # T1: an infinite decorative animation must really be running, or T2 proves nothing.
        pulse = state['pulse']
        assert isinstance(pulse, dict), f"no running animation found: {state!r}"
        assert float(str(pulse['duration']).rstrip('s')) > 0.1, (
            f"expected a real animation duration, got {pulse['duration']!r}"
        )
        assert pulse['iterations'] == 'infinite', (
            f"expected an infinite decorative animation, got {pulse['iterations']!r}"
        )

        # T2: the browser parsed the guard, on the universal selector, with both caps present.
        # The minifier writes `.01ms` and `:after`, so compare numerically and loosely.
        guard = state['guard']
        assert isinstance(guard, dict), f"guard rule missing from the served CSS: {state!r}"
        assert 'prefers-reduced-motion' in guard['condition']
        assert ':after' in guard['selector'] and ':before' in guard['selector']
        assert _ms(guard['animationDuration']) == 0.01, guard
        assert guard['iterations'] == '1', guard
        assert _ms(guard['transitionDuration']) == 0.01, guard

        # T3: the guard must not disable animations outright; Radix overlays rely on animationend.
        assert guard['usesAnimationNone'] is False, (
            'the shipped guard must shorten animations, never remove them, or overlay unmounts break'
        )
    finally:
        if page is not None:
            client.close_page(page, ignore_errors=True)
        client.close()
