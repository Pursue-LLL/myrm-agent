"""Shared UI selectors for EvictedOutputDrawer Chrome E2E flows.

[INPUT]
- marker_line (for drawer content ready checks)

[OUTPUT]
- WAIT_PROGRESS_UI_DOM_JS, EXPAND_PROGRESS_PANEL_JS
- TERMINAL_PREVIEW_JS, VIEW_FULL_OUTPUT_JS
- drawer_ready_js, drawer_expired_js, evicted_request_probe_js

[POS]
SSOT selector/probe snippets for UECD READ/A1 Chrome E2E tests.
"""

from __future__ import annotations

import json

_PROGRESS_TOGGLE_TESTID = "progress-steps-toggle"
_VIEW_FULL_TESTID = "evicted-view-full-output"
_DRAWER_TESTID = "evicted-output-drawer"
_DRAWER_EXPIRED_TESTID = "evicted-output-expired"

WAIT_PROGRESS_UI_DOM_JS = f"""(() => {{
  const toggle = document.querySelector('[data-testid="{_PROGRESS_TOGGLE_TESTID}"]');
  const viewFull = document.querySelector('[data-testid="{_VIEW_FULL_TESTID}"]');
  return {{
    ready: !!toggle || !!viewFull,
    hasToggle: !!toggle,
    hasViewFull: !!viewFull,
  }};
}})()"""

EXPAND_PROGRESS_PANEL_JS = f"""(() => {{
  const viewFull = document.querySelector('[data-testid="{_VIEW_FULL_TESTID}"]');
  if (viewFull) return {{ ready: true, alreadyVisible: true }};
  const toggle = document.querySelector('[data-testid="{_PROGRESS_TOGGLE_TESTID}"]');
  if (!(toggle instanceof HTMLElement)) {{
    return {{ ready: false, reason: 'progress-toggle-missing' }};
  }}
  const expanded = toggle.getAttribute('data-expanded') === 'true';
  if (expanded) {{
    return {{ ready: true, alreadyExpanded: true }};
  }}
  toggle.click();
  return {{ ready: true, clicked: true, action: 'expand' }};
}})()"""

TERMINAL_PREVIEW_JS = """(() => {
  const panel = document.querySelector('[data-testid="progress-steps-panel"]');
  if (!(panel instanceof HTMLElement)) {
    return { ready: false, reason: 'progress-panel-missing' };
  }
  const text = panel.innerText || '';
  const hasTruncated = /LARGE OUTPUT TRUNCATED|输出已截断|出力を切り詰め/.test(text);
  return { ready: hasTruncated, preview: text.slice(0, 400) };
})()"""

VIEW_FULL_OUTPUT_JS = f"""(() => {{
  const btn = document.querySelector('[data-testid="{_VIEW_FULL_TESTID}"]');
  if (!(btn instanceof HTMLElement)) return {{ ready: false, clicked: false }};
  btn.click();
  return {{ ready: true, clicked: true }};
}})()"""

CLEAR_RESOURCE_TIMINGS_JS = """(() => {
  try {
    performance.clearResourceTimings();
  } catch {
    // ignore
  }
  return { ready: true };
})()"""


def drawer_ready_js(marker_line: str) -> str:
    encoded = json.dumps(marker_line)
    return f"""(() => {{
  const drawer = document.querySelector('[data-testid="{_DRAWER_TESTID}"]');
  if (!(drawer instanceof HTMLElement)) {{
    return {{ ready: false, reason: 'drawer-missing' }};
  }}
  const text = drawer.innerText || '';
  return {{
    ready: text.includes({encoded}),
    hasDrawer: true,
    sample: text.slice(0, 500),
  }};
}})()"""


def drawer_expired_js() -> str:
    return f"""(() => {{
  const drawer = document.querySelector('[data-testid="{_DRAWER_TESTID}"]');
  if (!(drawer instanceof HTMLElement)) {{
    return {{ ready: false, hasDrawer: false, hasExpired: false }};
  }}
  const expired = drawer.querySelector('[data-testid="{_DRAWER_EXPIRED_TESTID}"]');
  return {{
    ready: !!expired,
    hasDrawer: true,
    hasExpired: !!expired,
    sample: (drawer.textContent || '').slice(0, 400),
  }};
}})()"""


def evicted_request_probe_js(*, expected_offset: int = 0, expected_limit: int = 500) -> str:
    """Probe browser resource entries for evicted API pagination params."""
    target_offset = max(0, expected_offset)
    target_limit = max(1, expected_limit)
    return f"""(() => {{
  const expectedOffset = String({target_offset});
  const expectedLimit = String({target_limit});
  const requests = performance
    .getEntriesByType('resource')
    .map((entry) => (entry && typeof entry.name === 'string' ? entry.name : ''))
    .filter((name) => name.includes('/api/v1/files/evicted?'))
    .map((name) => {{
      try {{
        const parsed = new URL(name, window.location.origin);
        return {{
          url: name,
          offset: parsed.searchParams.get('offset'),
          limit: parsed.searchParams.get('limit'),
        }};
      }} catch {{
        return {{ url: name, offset: null, limit: null }};
      }}
    }});
  const hit = requests.some(
    (item) => item.offset === expectedOffset && item.limit === expectedLimit,
  );
  const hasLimitZero = requests.some((item) => item.limit === '0');
  return {{
    ready: hit,
    hit,
    hasLimitZero,
    requestCount: requests.length,
    sample: requests.slice(-5),
  }};
}})()"""
