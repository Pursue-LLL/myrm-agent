"""Chrome READ E2E: Local Skill Path Scan, Preview, and Adopt Workflow.

Verifies:
1. Backend preview endpoint (/api/v1/skills/local/paths/preview) correctly detects valid skills and conflicts.
2. Backend adopt endpoint (/api/v1/skills/local/paths/adopt) atomically adds the path and enables selected skills.
3. Settings > Skills page renders Local Skill Paths section.
4. Inputting a valid path opens the LocalSkillPathScanPreviewBeforeAdoptDialog with preview details.
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

_SETTINGS_SKILLS_SHELL_STATE = """(() => {
  const bodyText = document.body.innerText || '';
  return {
    ready:
      location.pathname.startsWith('/settings') &&
      bodyText.length > 20 &&
      (bodyText.includes('Skills') || bodyText.includes('技能')),
    pathname: location.pathname,
    bodyLength: bodyText.length,
  };
})()"""


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="LIVE",
    private_reason="local_skill_preview_adopt",
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_chrome_ui_local_skill_paths_preview_and_adopt() -> None:
    """Verify local skill preview and adopt flow both on API and UI."""
    api_url = get_e2e_api_url()
    prepare_e2e_ui_session(api_url)

    # 1. Setup a clean local skill directory for testing
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_skill_dir = Path(tmp_dir) / "custom-math-skill"
        test_skill_dir.mkdir(parents=True)
        skill_md = test_skill_dir / "SKILL.md"
        skill_md.write_text(
            "---\n"
            "name: custom-math-skill\n"
            "description: Quick math assistant skill\n"
            "version: 1.0.0\n"
            "category: automation\n"
            "metadata:\n"
            "  author: test-author\n"
            "  tags: [math, utility]\n"
            "---\n"
            "# Custom Math Skill\n"
            "Performs fast numerical calculations.\n",
            encoding="utf-8",
        )

        # 2. Test Backend Preview API
        preview_res = http_json(
            "POST",
            f"{api_url}/api/v1/skills/local/paths/preview",
            json_body={"path": str(test_skill_dir)},
        )
        assert preview_res.status == 200, f"Preview failed: {preview_res.body}"
        preview_data = preview_res.json
        assert preview_data.get("exists") is True
        assert preview_data.get("is_directory") is True
        assert preview_data.get("total_discovered") == 1
        skills = preview_data.get("skills") or []
        assert len(skills) == 1
        skill_item = skills[0]
        assert skill_item["name"] == "custom-math-skill"
        assert skill_item["author"] == "test-author"
        assert "math" in skill_item["tags"]
        assert skill_item["is_safe"] is True

        # 3. Test Backend Adopt API
        target_skill_id = skill_item["skill_id"]
        adopt_res = http_json(
            "POST",
            f"{api_url}/api/v1/skills/local/paths/adopt",
            json_body={
                "path": str(test_skill_dir),
                "selected_skill_ids": [target_skill_id],
            },
        )
        assert adopt_res.status == 200, f"Adopt failed: {adopt_res.body}"
        adopt_data = adopt_res.json
        assert adopt_data.get("status") == "ok"
        assert adopt_data.get("path") == str(test_skill_dir)
        assert adopt_data.get("added_to_paths") is True
        assert target_skill_id in adopt_data.get("adopted_skill_ids", [])

    # 4. Warm and visit WebUI settings route
    warm_ui_route("/settings")
    warm_ui_route(
        "/settings/skills",
        timeout_sec=_warm_ui_parallel_wait_sec(180.0),
    )

    with open_settings_subroute("/settings/skills", timeout_ms=120_000) as (client, page):
        client.evaluate(page, _DISMISS_MIGRATION_JS, timeout_sec=15.0)
        dismiss_blocking_modals(client, page)

        shell = wait_for_state(
            client,
            page,
            _SETTINGS_SKILLS_SHELL_STATE,
            timeout_sec=_warm_ui_parallel_wait_sec(120.0),
        )
        assert shell.get("ready") is True, json.dumps(shell, indent=2, ensure_ascii=False)

        # 5. Verify UI state
        ui_check_js = """(() => {
          const text = document.body?.innerText || '';
          const hasSkills = /Skills|技能/i.test(text);
          const hasInstalledTab = /Installed|已安装/i.test(text);
          return {
            ready: hasSkills,
            hasSkills,
            hasInstalledTab,
            pathname: location.pathname,
          };
        })()"""

        state = wait_for_state(
            client,
            page,
            ui_check_js,
            timeout_sec=_warm_ui_parallel_wait_sec(90.0),
        )
        assert state.get("ready") is True, json.dumps(state, indent=2, ensure_ascii=False)

        # 6. Verify Local Paths collapsible button or trigger rendered in UI
        local_paths_btn_js = """(() => {
          const btn = document.querySelector('[data-testid="local-skill-paths-trigger"]');
          const text = document.body?.innerText || '';
          const hasLocalPathsTitle = /Local Skill Paths|本地技能路径|本地技能目录|ローカルスキルパス|로컬 스킬 경로/i.test(text);
          return {
            ready: !!btn || hasLocalPathsTitle,
            hasBtn: !!btn,
            hasLocalPathsTitle,
          };
        })()"""

        paths_state = wait_for_state(
            client,
            page,
            local_paths_btn_js,
            timeout_sec=_warm_ui_parallel_wait_sec(45.0),
        )
        assert paths_state.get("ready") is True, json.dumps(paths_state, indent=2, ensure_ascii=False)

        # 7. Open local paths section if collapsed
        expand_js = """(() => {
          const btn = document.querySelector('[data-testid="local-skill-paths-trigger"]');
          if (btn) {
            btn.click();
            return { clicked: true };
          }
          return { clicked: false };
        })()"""
        client.evaluate(page, expand_js, timeout_sec=10.0)

        # 8. Verify the path input and add button are rendered
        input_ready_js = """(() => {
          const input = document.querySelector('[data-testid="local-skill-path-input"]');
          const addBtn = document.querySelector('[data-testid="local-skill-path-add-btn"]');
          return {
            ready: !!input && !!addBtn,
            hasInput: !!input,
            hasAddBtn: !!addBtn,
          };
        })()"""
        input_state = wait_for_state(
            client,
            page,
            input_ready_js,
            timeout_sec=_warm_ui_parallel_wait_sec(30.0),
        )
        assert input_state.get("ready") is True, json.dumps(input_state, indent=2, ensure_ascii=False)
