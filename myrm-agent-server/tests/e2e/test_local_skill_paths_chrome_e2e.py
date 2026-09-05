"""Chrome MCP E2E: Local Skill Paths & Preview in Settings > Skills.

Verifies:
1. Settings/Skills loads and Local Skill Paths card is visible
2. Live API endpoint /api/v1/skills/local/paths/preview works with realistic disk paths
3. Discovered skills, tags and safety status are validated
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from tests.support.chrome_mcp_e2e import (
    _warm_ui_parallel_wait_sec,
    dismiss_blocking_modals,
    get_e2e_api_url,
    http_json,
    open_settings_subroute,
    prepare_e2e_ui_session,
    wait_for_state,
    warm_ui_route,
)

_DISMISS_MIGRATION_JS = """(() => {
  try {
    sessionStorage.setItem('migration_discovery_dismissed', 'true');
    sessionStorage.setItem('competitor_migration_dismissed', 'true');
  } catch (err) {
    return { ok: false, err: String(err) };
  }
  return { ok: true };
})()"""

_SETTINGS_SHELL_STATE = """(() => {
  const bodyText = document.body.innerText || '';
  return {
    ready:
      location.pathname.startsWith('/settings') &&
      bodyText.length > 20 &&
      !!document.querySelector('[data-testid="settings-layout"]'),
    pathname: location.pathname,
    bodyLength: bodyText.length,
  };
})()"""

_LOCAL_SKILL_PATHS_CARD_JS = """(() => {
  const text = document.body?.innerText || '';
  const hasLocalPaths = /Local Skill Paths|本地技能目录|本地技能路径|ローカルスキル/i.test(text);
  const hasAddButton = Array.from(document.querySelectorAll('button')).some(b =>
    /Add|添加|追加/i.test(b.textContent || '')
  );
  return {
    ready: hasLocalPaths && hasAddButton,
    hasLocalPaths,
    hasAddButton,
    snippet: text.slice(0, 500),
  };
})()"""


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="LIVE",
    private_reason="live_shpoib",
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_chrome_ui_local_skill_paths_card_and_preview_live() -> None:
    api_url = get_e2e_api_url()
    prepare_e2e_ui_session(api_url)

    # 1. Test live backend preview API with realistic temporary skill directory
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        skill_content = (
            "---\n"
            "name: e2e-previewed-skill\n"
            "description: E2E realistic preview skill\n"
            "version: 1.0.0\n"
            "category: automation\n"
            "tags:\n"
            "  - e2e\n"
            "  - test\n"
            "---\n"
            "# E2E Instructions\n"
        )
        (tmp_path / "SKILL.md").write_text(skill_content, encoding="utf-8")

        res = http_json(
            "POST",
            f"{api_url}/api/v1/skills/local/paths/preview",
            json_body={"path": str(tmp_path)},
        )
        data = res.json
        assert isinstance(data, dict)
        assert data.get("exists") is True
        assert data.get("total_discovered") == 1
        skills = data.get("skills", [])
        assert len(skills) == 1
        assert skills[0]["name"] == "e2e-previewed-skill"
        assert "e2e" in skills[0]["tags"]
        assert skills[0]["is_safe"] is True

    # 2. Warm route and verify UI card renders in Settings > Skills
    warm_ui_route("/settings")
    warm_ui_route(
        "/settings/skills",
        timeout_sec=_warm_ui_parallel_wait_sec(180.0),
    )
    with open_settings_subroute(
        "/settings/skills",
        timeout_ms=120_000,
    ) as (client, page):
        client.evaluate(page, _DISMISS_MIGRATION_JS, timeout_sec=15.0)
        dismiss_blocking_modals(client, page)

        shell = wait_for_state(
            client,
            page,
            _SETTINGS_SHELL_STATE,
            timeout_sec=_warm_ui_parallel_wait_sec(120.0),
        )
        assert shell.get("ready") is True, json.dumps(shell, indent=2, ensure_ascii=False)

        state = wait_for_state(
            client,
            page,
            _LOCAL_SKILL_PATHS_CARD_JS,
            timeout_sec=_warm_ui_parallel_wait_sec(90.0),
        )
        assert state.get("ready") is True, json.dumps(state, indent=2, ensure_ascii=False)
        assert state.get("hasLocalPaths") is True
        assert state.get("hasAddButton") is True
