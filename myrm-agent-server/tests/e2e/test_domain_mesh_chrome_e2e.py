"""Real Chrome MCP E2E for Three-Domain Memory Mesh panel.

Covers the real-user flow on the settings memory page:
1. Open /settings/memory and confirm Three-Domain Memory Mesh renders.
2. Confirm the Multi-Domain Sync badge is displayed.
3. Confirm the user-facing description is rendered.
4. Confirm all three domain cards (User, Assistant, Task) are properly displayed.

The page opens in the tester's own language, so the words it must show are read from every shipped locale file; the
panel is ready when one language shows all of them.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.support.chrome_mcp_e2e import (
    open_settings_subroute,
    wait_for_state,
    warm_ui_route,
)

_LOCALES_DIR = Path(__file__).resolve().parents[3] / "myrm-agent-frontend" / "locales"

_DOMAIN_MESH_PANEL_READY_JS = """((copies) => {
  const text = document.body?.textContent || '';
  const shown = Object.fromEntries(
    Object.entries(copies).map(([language, copy]) => [
      language,
      Object.entries(copy).filter(([, words]) => text.includes(words)).map(([part]) => part),
    ]),
  );
  const language = Object.keys(copies).find((name) => shown[name].length === Object.keys(copies[name]).length);
  return {
    ready: Boolean(language),
    language: language ?? null,
    shown,
    path: location.pathname,
    visibleText: (document.body?.innerText || '').slice(0, 600),
  };
})"""


def _mesh_copy_by_language() -> dict[str, dict[str, str]]:
    """Title, badge, description and the three domain names the panel shows, per shipped language."""
    copies: dict[str, dict[str, str]] = {}
    for locale_file in sorted(_LOCALES_DIR.glob("*.json")):
        mesh = json.loads(locale_file.read_text(encoding="utf-8"))["memory"]["mesh"]
        copies[locale_file.stem] = {
            "title": mesh["panel"]["title"],
            "badge": mesh["panel"]["badge"],
            "description": mesh["panel"]["description"],
            "user": mesh["domains"]["user"]["title"],
            "assistant": mesh["domains"]["assistant"]["title"],
            "task": mesh["domains"]["task"]["title"],
        }
    assert copies, f"no locale files under {_LOCALES_DIR}"
    return copies


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(180)
def test_three_domain_memory_mesh_chrome_e2e() -> None:
    """Real user flow: verify Three-Domain Memory Mesh panel copy, badge, and domain cards."""
    ready_js = f"({_DOMAIN_MESH_PANEL_READY_JS})({json.dumps(_mesh_copy_by_language(), ensure_ascii=False)})"
    warm_ui_route("/settings/memory")
    with open_settings_subroute("/settings/memory", timeout_ms=120_000) as (client, page):
        state = wait_for_state(client, page, ready_js, timeout_sec=90.0)
        assert state.get("ready") is True, state
        print(f"MESH_PANEL_LANGUAGE {state.get('language')}", flush=True)
