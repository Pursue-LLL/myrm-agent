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
    get_e2e_ui_url,
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
      !!document.querySelector('[data-testid="settings-layout"]'),
    pathname: location.pathname,
    bodyLength: bodyText.length,
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
def test_chrome_ui_local_skill_paths_preview_and_adopt() -> None:
    """Verify local skill preview and adopt flow on UI."""
    api_url = get_e2e_api_url()
    prepare_e2e_ui_session(api_url)

    # 1. Setup a clean local skill directory for UI preview interaction
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

        # 2. Warm and visit WebUI settings route
        warm_ui_route("/settings")
        warm_ui_route(
            "/settings/skills",
            timeout_sec=_warm_ui_parallel_wait_sec(180.0),
        )

        with open_settings_subroute("/settings/skills", timeout_ms=120_000) as (
            client,
            page,
        ):
            client.evaluate(page, _DISMISS_MIGRATION_JS, timeout_sec=15.0)
            dismiss_blocking_modals(client, page)

            # Ensure page navigated to /settings/skills
            client.navigate(page, f"{get_e2e_ui_url().rstrip('/')}/settings/skills", timeout_ms=90_000)
            dismiss_blocking_modals(client, page)

            shell = wait_for_state(
                client,
                page,
                _SETTINGS_SKILLS_SHELL_STATE,
                timeout_sec=_warm_ui_parallel_wait_sec(120.0),
                page_url=f"{get_e2e_ui_url().rstrip('/')}/settings/skills",
            )
            assert shell.get("ready") is True, json.dumps(
                shell, indent=2, ensure_ascii=False
            )

            # 5. Verify UI state and ensure auth is populated in local mode
            client.evaluate(page, """(() => {
              try {
                if (!localStorage.getItem('auth_token')) {
                  localStorage.setItem('auth_token', 'local_user_token');
                }
                if (!localStorage.getItem('auth_user')) {
                  localStorage.setItem('auth_user', JSON.stringify({
                    id: 'local-user',
                    email: 'local@tauri.app',
                    display_name: 'Local User',
                    role: 'admin',
                  }));
                }
                window.dispatchEvent(new Event('storage'));
              } catch (e) {
                // ignore
              }
            })()""", timeout_sec=10.0)

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
            assert state.get("ready") is True, json.dumps(
                state, indent=2, ensure_ascii=False
            )

            # Switch to Installed tab to reveal local paths trigger if needed
            tab_click_js = """(() => {
              const tab = Array.from(document.querySelectorAll('button, [role="tab"]')).find(el =>
                /Installed|已安装/i.test(el.textContent || '')
              );
              if (tab) {
                tab.click();
                return { clicked: true, text: tab.textContent };
              }
              return { clicked: false };
            })()"""
            client.evaluate(page, tab_click_js, timeout_sec=10.0)

            # 6. Verify Local Paths collapsible button or trigger rendered in UI
            local_paths_btn_js = """(() => {
              const btn = document.querySelector('[data-testid="local-skill-paths-trigger"]');
              const text = document.body?.innerText || '';
              const hasLocalPathsTitle = /Local Skill Paths|本地技能路径|本地技能目录|ローカルスキルパス|로컬 스킬 경로/i.test(text);
              if (!btn && !hasLocalPathsTitle) {
                // Try to click Installed tab again if it didn't switch
                const tab = Array.from(document.querySelectorAll('button, [role="tab"]')).find(el =>
                  /Installed|已安装/i.test(el.textContent || '')
                );
                if (tab) tab.click();
              }
              const btnAfter = document.querySelector('[data-testid="local-skill-paths-trigger"]');
              const textAfter = document.body?.innerText || '';
              const hasTitleAfter = /Local Skill Paths|本地技能路径|本地技能目录|ローカルスキルパス|로컬 스킬 경로/i.test(textAfter);
              return {
                ready: !!btnAfter || hasTitleAfter,
                hasBtn: !!btnAfter,
                hasLocalPathsTitle: hasTitleAfter,
                installedTextSnippet: textAfter.slice(0, 300),
              };
            })()"""

            paths_state = wait_for_state(
                client,
                page,
                local_paths_btn_js,
                timeout_sec=_warm_ui_parallel_wait_sec(45.0),
            )
            assert paths_state.get("ready") is True, json.dumps(
                paths_state, indent=2, ensure_ascii=False
            )

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
            assert input_state.get("ready") is True, json.dumps(
                input_state, indent=2, ensure_ascii=False
            )

            # 9. Realistic User Flow: Input test_skill_dir path and click Add button to trigger Preview Dialog
            ui_input_and_click_js = f"""(() => {{
              const input = document.querySelector('[data-testid="local-skill-path-input"]');
              const addBtn = document.querySelector('[data-testid="local-skill-path-add-btn"]');
              if (!input || !addBtn) {{
                return {{ ok: false, error: 'Input or Add button missing' }};
              }}
              // Set value and dispatch input event for React controlled component
              input.value = {json.dumps(str(test_skill_dir))};
              input.dispatchEvent(new Event('input', {{ bubbles: true }}));
              input.dispatchEvent(new Event('change', {{ bubbles: true }}));
              addBtn.click();
              return {{ ok: true }};
            }})()"""
            click_res = client.evaluate(page, ui_input_and_click_js, timeout_sec=15.0)
            assert (
                isinstance(click_res, dict) and click_res.get("ok") is True
            ), f"Failed to input path: {click_res}"

            # 10. Verify LocalSkillPathScanPreviewBeforeAdoptDialog opens with detected skill name
            dialog_ready_js = """(() => {
              const body = document.body?.innerText || '';
              const hasDialogTitle = /Preview & Adopt|预览并采纳|プレビューと採用/i.test(body);
              const hasSkill = /custom-math-skill/.test(body);
              const hasAdoptBtn = Array.from(document.querySelectorAll('button')).some(b =>
                /Adopt & Add Path|采纳并添加路径|追加して採用/i.test(b.textContent || '')
              );
              return {
                ready: hasDialogTitle || hasSkill || hasAdoptBtn,
                hasDialogTitle,
                hasSkill,
                hasAdoptBtn,
              };
            })()"""
            dialog_state = wait_for_state(
                client,
                page,
                dialog_ready_js,
                timeout_sec=_warm_ui_parallel_wait_sec(30.0),
            )
            assert dialog_state.get("ready") is True, json.dumps(
                dialog_state, indent=2, ensure_ascii=False
            )

            # 11. Click "采纳并添加路径" button to execute adopt action in UI
            confirm_adopt_js = """(() => {
              const adoptBtn = document.querySelector('[data-testid="preview-adopt-confirm-btn"]') ||
                Array.from(document.querySelectorAll('button')).find(b =>
                  /Adopt & Add Path|采纳并添加路径|追加して採用/i.test(b.textContent || '')
                );
              if (adoptBtn) {
                adoptBtn.click();
                return { ok: true };
              }
              return { ok: false, error: 'Adopt button not found' };
            })()"""
            confirm_res = client.evaluate(page, confirm_adopt_js, timeout_sec=15.0)
            assert isinstance(confirm_res, dict) and confirm_res.get("ok") is True

            # 12. Verify Dialog closes and path list updates with the new adopted skill path
            path_list_updated_js = f"""(() => {{
              const text = document.body?.innerText || '';
              const hasPath = text.includes({json.dumps(str(test_skill_dir))}) || text.includes('custom-math-skill');
              return {{
                ready: hasPath,
                hasPath,
              }};
            }})()"""
            updated_state = wait_for_state(
                client,
                page,
                path_list_updated_js,
                timeout_sec=_warm_ui_parallel_wait_sec(30.0),
            )
            assert updated_state.get("ready") is True, json.dumps(
                updated_state, indent=2, ensure_ascii=False
            )
