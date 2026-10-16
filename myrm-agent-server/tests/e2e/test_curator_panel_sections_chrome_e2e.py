"""Real Chrome MCP E2E for the Curator panel's run history and skill-doctor sections in Settings > Skills.

[INPUT]
- tests.support.chrome_mcp_e2e::(open_settings_subroute, wait_for_state, dismiss_blocking_modals) (POS: owned Chrome page + state polling)

[OUTPUT]
- test_curator_sections_read_in_plain_language_in_both_themes_and_at_phone_width: the history and
  diagnostics sections in Chinese, light and dark, at desktop width and inside a 375px-wide frame

[POS]
UI-lane check of the two sections the Curator panel renders from server data. The history and diagnostics
responses are replaced in the page so every finding type and every transition phrase is on screen whatever
the machine's skills did this week; the server-side producers are covered by ``tests/api/skills``.
The phone width is a same-origin frame, so the page's own media queries run at 375px.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta

import pytest

from tests.support.chrome_mcp_e2e import (
    ChromeMcpClient,
    McpPage,
    _warm_ui_parallel_wait_sec,
    dismiss_blocking_modals,
    open_settings_subroute,
    wait_for_state,
    warm_ui_route,
)

_SKILL_PREFIX = "e2e-curator-skill-"
_MIN_TEXT_CONTRAST = 4.5

_DISMISS_MIGRATION_JS = """(() => {
  try {
    sessionStorage.setItem('migration_discovery_dismissed', 'true');
    sessionStorage.setItem('competitor_migration_dismissed', 'true');
  } catch (err) {
    return { ok: false, err: String(err) };
  }
  return { ok: true };
})()"""

_SETTINGS_SHELL_STATE = """(() => ({
  ready:
    location.pathname.startsWith('/settings') &&
    !!document.querySelector('[data-testid="settings-layout"]'),
}))()"""

# Everything the test does inside a window (the page itself or the phone-width frame) lives here, so both
# widths run the same code.
_DRIVER_JS = r"""(() => {
  if (window.__curatorE2E) return true;
  const press = (win, el) => {
    const opts = { bubbles: true, cancelable: true, composed: true, button: 0, detail: 1, view: win };
    el.dispatchEvent(new win.PointerEvent('pointerdown', { ...opts, pointerId: 1, isPrimary: true }));
    el.dispatchEvent(new win.MouseEvent('mousedown', opts));
    el.dispatchEvent(new win.PointerEvent('pointerup', { ...opts, pointerId: 1, isPrimary: true }));
    el.dispatchEvent(new win.MouseEvent('mouseup', opts));
    el.dispatchEvent(new win.MouseEvent('click', opts));
  };
  const tab = (win, name) =>
    win.document.querySelector(`[role="tab"][data-state][id$="trigger-${name}"]`);
  const probe = document.createElement('canvas').getContext('2d', { willReadFrequently: true });
  const rgba = (css) => {
    probe.clearRect(0, 0, 1, 1);
    probe.fillStyle = '#010203';
    probe.fillStyle = css;
    if (probe.fillStyle === '#010203' && css.replace(/\s/g, '') !== 'rgb(1,2,3)') return null;
    probe.fillRect(0, 0, 1, 1);
    const d = probe.getImageData(0, 0, 1, 1).data;
    return [d[0], d[1], d[2], d[3] / 255];
  };
  const over = (top, under) => {
    const a = top[3];
    return [0, 1, 2].map((i) => top[i] * a + under[i] * (1 - a)).concat([1]);
  };
  const luminance = ([r, g, b]) => {
    const lin = (v) => ((v /= 255) <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4);
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
  };
  const effectiveBackground = (win, el) => {
    const layers = [];
    for (let n = el; n; n = n.parentElement) {
      const c = rgba(win.getComputedStyle(n).backgroundColor);
      if (c && c[3] > 0) layers.push(c);
      if (c && c[3] >= 1) break;
    }
    let acc = layers.length && layers[layers.length - 1][3] >= 1 ? layers.pop() : [255, 255, 255, 1];
    while (layers.length) acc = over(layers.pop(), acc);
    return acc;
  };
  const inheritedOpacity = (win, el) => {
    let o = 1;
    for (let n = el; n; n = n.parentElement) o *= Number(win.getComputedStyle(n).opacity);
    return o;
  };
  const ownText = (el) =>
    Array.from(el.childNodes).some((n) => n.nodeType === 3 && n.textContent.trim());

  window.__curatorE2E = {
    install(win) {
      if (win.__curatorStub) return;
      const orig = win.fetch.bind(win);
      win.__curatorStub = { history: 0, diagnostics: 0 };
      win.fetch = async (input, init) => {
        const url = String(input && typeof input === 'object' && 'url' in input ? input.url : input);
        const key = url.includes('/curator/history')
          ? 'history'
          : url.includes('/curator/diagnostics')
            ? 'diagnostics'
            : null;
        if (!key) return orig(input, init);
        win.__curatorStub[key] += 1;
        return new win.Response(JSON.stringify(window.__CURATOR_FIXTURE__[key]), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      };
    },
    showTab(win, name) {
      const el = tab(win, name);
      if (el && el.getAttribute('data-state') !== 'active') press(win, el);
      return !!el && el.getAttribute('data-state') === 'active';
    },
    openHistory(win) {
      const doc = win.document;
      const toggle = doc.querySelector('[data-testid="curator-history-toggle"]');
      if (toggle && !doc.querySelector('[data-testid="curator-history-entry"]')) press(win, toggle);
    },
    setTheme(win, mode) {
      win.document.documentElement.classList.toggle('dark', mode === 'dark');
    },
    settled(win) {
      return win.document.getAnimations().every((a) => !(a instanceof win.CSSTransition));
    },
    snapshot(win) {
      const doc = win.document;
      const texts = (selector) =>
        Array.from(doc.querySelectorAll(selector)).map((el) => (el.innerText || '').replace(/\s+/g, ' ').trim());
      return {
        dark: doc.documentElement.classList.contains('dark'),
        stub: win.__curatorStub || null,
        header: (doc.querySelector('[data-testid="curator-diagnostics"]')?.innerText || '').replace(/\s+/g, ' '),
        entries: texts('[data-testid="curator-history-entry"]'),
        rows: texts('[data-testid="curator-diagnostic-row"]'),
        rowButtons: Array.from(doc.querySelectorAll('[data-testid="curator-diagnostic-row"]')).map(
          (row) => row.querySelectorAll('button').length
        ),
        sectionsText: ['curator-history', 'curator-diagnostics']
          .map((id) => doc.querySelector(`[data-testid="${id}"]`)?.innerText || '')
          .join('\n'),
      };
    },
    audit(win) {
      const doc = win.document;
      const panel = doc.querySelector('[data-testid="curator-panel"]');
      const sections = ['curator-history', 'curator-diagnostics']
        .map((id) => doc.querySelector(`[data-testid="${id}"]`))
        .filter(Boolean);
      const viewport = win.innerWidth;
      const outside = [];
      const lowContrast = [];
      let measured = 0;
      let unmeasurable = 0;
      for (const root of sections) {
        for (const el of root.querySelectorAll('*')) {
          const rect = el.getBoundingClientRect();
          if (rect.width > 0 && (rect.right > viewport + 1 || rect.left < -1)) {
            outside.push(`${el.tagName.toLowerCase()}:${(el.innerText || '').slice(0, 30)}`);
          }
          if (!ownText(el) || rect.width === 0) continue;
          const fg = rgba(win.getComputedStyle(el).color);
          if (!fg) { unmeasurable += 1; continue; }
          const bg = effectiveBackground(win, el);
          fg[3] *= inheritedOpacity(win, el);
          const shown = over(fg, bg);
          const [hi, lo] = [luminance(shown), luminance(bg)].sort((a, b) => b - a);
          const ratio = (hi + 0.05) / (lo + 0.05);
          measured += 1;
          if (ratio < __MIN_CONTRAST__) {
            lowContrast.push({
              text: (el.innerText || '').slice(0, 24),
              ratio: Math.round(ratio * 100) / 100,
              size: win.getComputedStyle(el).fontSize,
            });
          }
        }
      }
      return {
        viewport,
        panelScrollOverflow: panel ? panel.scrollWidth - panel.clientWidth : null,
        outside,
        measured,
        unmeasurable,
        lowContrast,
      };
    },
  };
  return true;
})()""".replace("__MIN_CONTRAST__", str(_MIN_TEXT_CONTRAST))

_PHONE_FRAME_JS = """(() => {
  let frame = document.getElementById('curator-phone-frame');
  if (!frame) {
    frame = document.createElement('iframe');
    frame.id = 'curator-phone-frame';
    frame.src = '/settings/skills';
    frame.style.cssText =
      'position:fixed;top:0;left:0;width:375px;height:812px;border:0;z-index:2147483647;background:#fff';
    document.body.appendChild(frame);
  }
  const win = frame.contentWindow;
  const doc = win && win.document;
  const hasLayout = !!doc && !!doc.querySelector('[data-testid="settings-layout"]');
  return {
    ready: hasLayout && win.location.pathname.startsWith('/settings'),
    width: win ? win.innerWidth : null,
    path: win ? win.location.pathname : null,
    readyState: doc ? doc.readyState : null,
    hasLayout,
    bodyStart: doc && doc.body ? (doc.body.innerText || '').slice(0, 120) : null,
  };
})()"""

_PHONE_WINDOW = "document.getElementById('curator-phone-frame').contentWindow"


def _fixture() -> dict[str, object]:
    """One finding per type code and transitions for each of the three reason phrases (stale and archive share one)."""
    now = datetime.now(UTC)

    def stamp(delta: timedelta) -> str:
        return (now - delta).isoformat()

    def transition(name: str, to_status: str, reason: str) -> dict[str, str]:
        return {
            "skill_name": f"{_SKILL_PREFIX}{name}",
            "from_status": "active" if to_status == "stale" else "stale",
            "to_status": to_status,
            "reason": reason,
        }

    return {
        "history": [
            {
                "timestamp": stamp(timedelta(hours=2)),
                "trigger": "background",
                "skills_scanned": 24,
                "total_transitions": 0,
                "stale_count": 0,
                "archived_count": 0,
                "transitions": [],
            },
            {
                "timestamp": stamp(timedelta(days=3)),
                "trigger": "manual",
                "skills_scanned": 24,
                "total_transitions": 4,
                "stale_count": 2,
                "archived_count": 2,
                "transitions": [
                    transition("ppt", "stale", "stale"),
                    transition("scraper", "stale", "low_quality"),
                    transition("report", "archived", "archive"),
                    transition("extra", "archived", "lru_eviction"),
                ],
            },
        ],
        "diagnostics": {
            "health_score": 70,
            "findings": [
                {
                    "skill_name": f"{_SKILL_PREFIX}ocr",
                    "finding_type": "wrong_but_frequent",
                    "severity": "critical",
                    "call_count": 30,
                    "success_rate": 0.1,
                    "pinned": False,
                    "details": {"observed_count": 30, "success_count": 3, "failure_count": 27, "trust": "trusted"},
                },
                {
                    "skill_name": f"{_SKILL_PREFIX}notes",
                    "finding_type": "stale_pinned",
                    "severity": "info",
                    "call_count": 3,
                    "success_rate": 1.0,
                    "pinned": True,
                    "details": {"days_inactive": 45},
                },
                {
                    "skill_name": "[Library Bloat]",
                    "finding_type": "hoarding_bloat",
                    "severity": "warning",
                    "call_count": 0,
                    "success_rate": 1.0,
                    "pinned": False,
                    "details": {"active_count": 52, "max_skills": 50, "excess": 2},
                },
            ],
        },
    }


# Plain-language zh copy each section must show: transitions say what happened and why, findings are sentences.
_ZH_HISTORY_NEWEST = ("2小时前",)
_ZH_HISTORY_OLDER = (
    "3天前",
    "闲置 2",
    "已归档 2",
    f"{_SKILL_PREFIX}ppt → 闲置(长期未使用)",
    f"{_SKILL_PREFIX}scraper → 闲置(成功率偏低)",
    f"{_SKILL_PREFIX}report → 已归档(长期未使用)",
    f"{_SKILL_PREFIX}extra → 已归档(超出技能数量上限)",
)
_ZH_DIAGNOSTIC_ROWS = (
    (f"{_SKILL_PREFIX}ocr", "高频低效", "已运行 30 次，成功率仅 10%"),
    (f"{_SKILL_PREFIX}notes", "闲置置顶", "已固定，但已有 45 天未使用"),
    ("技能囤积", "活跃技能 52 个，比上限 50 个多出 2 个"),
)
_LEAKED = re.compile(
    r"PINNED|Score|\bstale\b|\barchived\b|inactive|low_quality|lru_eviction|wrong_but_frequent|stale_pinned"
    r"|hoarding_bloat|Library Bloat|\bago\b|\d\s?ms\b|settings\.skills|historyReason|doctor\."
)


def _evaluate(client: ChromeMcpClient, page: McpPage, script: str) -> object:
    return client.evaluate(page, script, timeout_sec=30.0)


def _evaluate_dict(client: ChromeMcpClient, page: McpPage, expression: str) -> dict[str, object]:
    value = _evaluate(client, page, f"(() => {expression})()")
    assert isinstance(value, dict), value
    return value


def _state_of(client: ChromeMcpClient, page: McpPage, expression: str, *, timeout_sec: float = 90.0) -> dict[str, object]:
    state = wait_for_state(client, page, expression, timeout_sec=_warm_ui_parallel_wait_sec(timeout_sec))
    assert state.get("ready") is True, json.dumps(state, indent=2, ensure_ascii=False)
    return state


def _bring_up_sections(client: ChromeMcpClient, page: McpPage, target: str) -> None:
    """Install the stub while the panel is not mounted, then mount it and open the history."""
    e2e = "window.__curatorE2E"
    # The rest of the state is only for the failure message: it says whether the tabs never mounted or never activated.
    _state_of(
        client,
        page,
        f"""(() => {{
          const win = {target};
          return {{
            ready: {e2e}.showTab(win, 'discover'),
            tabs: Array.from(win.document.querySelectorAll('[role="tab"]')).map(
              (t) => t.id.split('trigger-')[1] + ':' + t.getAttribute('data-state'),
            ),
            path: win.location.pathname,
            readyState: win.document.readyState,
            bodyStart: (win.document.body.innerText || '').slice(0, 120),
          }};
        }})()""",
    )
    assert _evaluate(client, page, f"(() => {{ {e2e}.install({target}); return true; }})()") is True
    _state_of(
        client,
        page,
        f"""(() => {{
          {e2e}.showTab({target}, 'installed');
          {e2e}.openHistory({target});
          const s = {e2e}.snapshot({target});
          return {{ ready: s.rows.length === 3 && s.entries.length === 2, rows: s.rows.length, entries: s.entries.length }};
        }})()""",
    )


def _check_copy(snapshot: dict[str, object]) -> None:
    stub = snapshot["stub"]
    assert isinstance(stub, dict) and stub["history"] >= 1 and stub["diagnostics"] >= 1, "data must come from the stub"
    entries, rows = snapshot["entries"], snapshot["rows"]
    assert isinstance(entries, list) and isinstance(rows, list)

    for expected in _ZH_HISTORY_NEWEST:
        assert expected in entries[0], (expected, entries[0])
    for expected in _ZH_HISTORY_OLDER:
        assert expected in entries[1], (expected, entries[1])

    header = str(snapshot["header"])
    assert "技能健康体检：发现 3 个异常" in header and "70/100" in header, header
    for row, fragments in zip(rows, _ZH_DIAGNOSTIC_ROWS, strict=True):
        for fragment in fragments:
            assert fragment in row, (fragment, row)
    assert "[Library Bloat]" not in rows[2], "the library-wide finding names no skill"
    assert snapshot["rowButtons"] == [2, 2, 0], "skill findings offer actions, the library-wide one offers none"

    assert not _LEAKED.search(str(snapshot["sectionsText"])), snapshot["sectionsText"]


def _layout_problems(audit: dict[str, object], *, label: str) -> list[str]:
    problems: list[str] = []
    if audit["outside"]:
        problems.append(f"{label}: elements outside the viewport: {audit['outside']}")
    overflow = audit["panelScrollOverflow"]
    if not isinstance(overflow, int) or overflow > 0:
        problems.append(f"{label}: panel scrolls sideways by {overflow}px")
    if not audit["measured"] or audit["unmeasurable"]:
        problems.append(f"{label}: contrast not measurable: measured={audit['measured']} unmeasurable={audit['unmeasurable']}")
    low = audit["lowContrast"]
    assert isinstance(low, list)
    problems.extend(
        f"{label}: {item['text']!r} {item['ratio']}:1 at {item['size']} (needs {_MIN_TEXT_CONTRAST}:1)" for item in low
    )
    return problems


def _check_both_themes(client: ChromeMcpClient, page: McpPage, target: str, *, label: str) -> list[str]:
    """Assert the copy in each theme and return every layout/contrast problem found, so one run shows them all."""
    e2e = "window.__curatorE2E"
    problems: list[str] = []
    for mode in ("dark", "light"):
        assert _evaluate(client, page, f"(() => {{ {e2e}.setTheme({target}, '{mode}'); return true; }})()") is True
        _state_of(
            client,
            page,
            f"(() => ({{ ready: {e2e}.settled({target}) && {e2e}.snapshot({target}).dark === {str(mode == 'dark').lower()} }}))()",
        )
        _check_copy(_evaluate_dict(client, page, f"{e2e}.snapshot({target})"))
        problems += _layout_problems(_evaluate_dict(client, page, f"{e2e}.audit({target})"), label=f"{label}/{mode}")
    return problems


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="READ", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_curator_sections_read_in_plain_language_in_both_themes_and_at_phone_width() -> None:
    warm_ui_route("/settings")
    warm_ui_route("/settings/skills", timeout_sec=_warm_ui_parallel_wait_sec(180.0))
    with open_settings_subroute("/settings/skills", timeout_ms=120_000) as (client, page):
        _evaluate(client, page, _DISMISS_MIGRATION_JS)
        dismiss_blocking_modals(client, page)
        _state_of(client, page, _SETTINGS_SHELL_STATE, timeout_sec=120.0)

        assert _evaluate(client, page, _DRIVER_JS) is True
        assert (
            _evaluate(client, page, f"(() => {{ window.__CURATOR_FIXTURE__ = {json.dumps(_fixture())}; return true; }})()")
            is True
        )

        _bring_up_sections(client, page, "window")
        problems = _check_both_themes(client, page, "window", label="desktop")
        # Printed now so a failure in the phone stage still shows what the desktop measured.
        print(f"E2E_CURATOR_DESKTOP_PROBLEMS: {json.dumps(problems, ensure_ascii=False)}", flush=True)

        phone = _state_of(client, page, _PHONE_FRAME_JS, timeout_sec=180.0)
        assert phone["width"] == 375, phone
        _bring_up_sections(client, page, _PHONE_WINDOW)
        problems += _check_both_themes(client, page, _PHONE_WINDOW, label="phone")

        assert not problems, "\n" + "\n".join(problems)
