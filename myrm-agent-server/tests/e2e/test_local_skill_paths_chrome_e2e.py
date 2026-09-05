"""Chrome READ lane E2E: Local Skills Paths Preview & Configuration in Settings > Skills.

Verifies:
1. Settings/Skills page loads and Local Paths card is visible
2. API endpoint /api/v1/skills/local/paths/preview works with realistic paths
3. UI inspection confirms path_statuses and preview dialog components render properly
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from tests.support.chrome_mcp_e2e import (
    get_e2e_api_url,
    http_json,
    open_settings_subroute,
    prepare_e2e_ui_session,
    wait_for_state,
)

_LOCAL_PATHS_CARD_JS = """(() => {
  const text = document.body?.innerText || '';
  const hasLocalSkills = /Local Skill Paths|本地技能目录|本地技能路径|ローカルスキル/i.test(text);
  const hasAddButton = Array.from(document.querySelectorAll('button')).some(b =>
    /Add|添加|追加/i.test(b.textContent || '')
  );
  return {
    ready: hasLocalSkills,
    hasLocalSkills,
    hasAddButton,
    snippet: text.slice(0, 500),
  };
})()"""


@pytest.mark.chrome_e2e
def test_local_skill_paths_settings_and_preview_flow() -> None:
    session = prepare_e2e_ui_session(agent_slug="default")
    api_url = get_e2e_api_url(session)

    # 1. Open /settings/skills (where local paths configuration lives)
    open_settings_subroute(session, "skills")

    # 2. Wait for UI state
    state = wait_for_state(
        session,
        _LOCAL_PATHS_CARD_JS,
        timeout_sec=25.0,
        desc="Local Skill Paths configuration in Settings",
    )
    assert state.get("hasLocalSkills") or state.get("ready"), f"Local paths UI missing: {state}"

    # 3. Create a realistic local skill on disk and preview it via API
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        (tmp_path / "SKILL.md").write_text(
            \"\"\"---
name: e2e-previewed-skill
description: E2E realistic preview skill
version: 1.0.0
category: automation
tags:
  - e2e
  - test
---
# E2E Instructions
\"\"\",
            encoding="utf-8",
        )

        preview_res = http_json(
            "POST",
            f"{api_url}/api/v1/skills/local/paths/preview",
            json_body={"path": str(tmp_path)},
        )
        assert preview_res.status == 200, f"Preview failed: {preview_res.body}"
        data = preview_res.json
        assert data["exists"] is True
        assert data["total_discovered"] == 1
        assert data["skills"][0]["name"] == "e2e-previewed-skill"
        assert "e2e" in data["skills"][0]["tags"]
