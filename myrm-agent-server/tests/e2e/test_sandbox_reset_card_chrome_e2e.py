"""Chrome READ E2E: Settings > System in local mode shows no sandbox reset card.

The card is a sandbox-only control: in local mode its endpoint answers 403, so showing it would hand the user a
button that can only fail. The System page imports the card module, so rendering the page in a real browser also
proves the module compiles and mounts under the real Next dev server. A sandbox-mode page needs the control plane
and a container runtime, neither of which a local stack has, so only the local-mode contract is checked here.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.support.chrome_mcp_e2e import (
    _warm_ui_parallel_wait_sec,
    dismiss_blocking_modals,
    get_e2e_api_url,
    open_settings_subroute,
    prepare_e2e_ui_session,
    wait_for_state,
    warm_ui_route,
)

_LOCALES_DIR = Path(__file__).resolve().parents[3] / "myrm-agent-frontend" / "locales"
_LOCALES = ("en", "zh", "zh-TW", "ja", "ko", "de")

_DISMISS_MIGRATION_JS = """(() => {
  try {
    sessionStorage.setItem('migration_discovery_dismissed', 'true');
    sessionStorage.setItem('competitor_migration_dismissed', 'true');
  } catch (err) {
    return { ok: false, err: String(err) };
  }
  return { ok: true };
})()"""


def _locale_values(*path: str) -> list[str]:
    """The string at `settings.system.<path>` in every shipped locale."""
    values: list[str] = []
    for locale in _LOCALES:
        node = json.loads((_LOCALES_DIR / f"{locale}.json").read_text(encoding="utf-8"))["settings"]["system"]
        for part in path:
            node = node[part]
        values.append(str(node))
    return values


def _system_page_state_js() -> str:
    """Whether the System page has finished rendering, and whether any locale's reset card title is on it."""
    storage_labels = _locale_values("config", "storageCurrentPath")
    reset_titles = _locale_values("sandboxReset", "title")
    return f"""(() => {{
  // Raw text nodes outside script/style: innerText would apply the heading's CSS uppercase, and body.textContent
  // would include the inline payload scripts that carry every translation string.
  const skipped = new Set(['SCRIPT', 'STYLE', 'NOSCRIPT', 'TEMPLATE']);
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, {{
    acceptNode: (node) =>
      node.parentElement && !skipped.has(node.parentElement.tagName) ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT,
  }});
  const texts = [];
  while (walker.nextNode()) texts.push(walker.currentNode.nodeValue);
  const bodyText = texts.join(' ');
  return {{
    ready:
      location.pathname.startsWith('/settings') &&
      !!document.querySelector('[data-testid="settings-layout"]') &&
      {json.dumps(storage_labels, ensure_ascii=False)}.some((label) => bodyText.includes(label)),
    resetCardShown: {json.dumps(reset_titles, ensure_ascii=False)}.some((title) => bodyText.includes(title)),
    pathname: location.pathname,
    bodyLength: bodyText.length,
  }};
}})()"""


@pytest.mark.chrome_e2e(
    execution_mode="SHARED",
    access_scope="READ",
    workload="STANDARD",
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_chrome_ui_local_mode_system_page_has_no_sandbox_reset_card() -> None:
    """The System page renders in a real browser and carries no sandbox-only reset card."""
    api_url = get_e2e_api_url()
    prepare_e2e_ui_session(api_url)

    warm_ui_route("/settings")
    warm_ui_route(
        "/settings/system",
        timeout_sec=_warm_ui_parallel_wait_sec(180.0),
    )
    with open_settings_subroute(
        "/settings/system",
        timeout_ms=120_000,
    ) as (client, page):
        client.evaluate(page, _DISMISS_MIGRATION_JS, timeout_sec=15.0)
        dismiss_blocking_modals(client, page)

        state = wait_for_state(
            client,
            page,
            _system_page_state_js(),
            timeout_sec=_warm_ui_parallel_wait_sec(120.0),
        )
        assert state.get("ready") is True, json.dumps(state, indent=2, ensure_ascii=False)
        assert state.get("resetCardShown") is False, json.dumps(state, indent=2, ensure_ascii=False)
