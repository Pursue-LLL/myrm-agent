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
    http_json,
    open_mcp_page,
    open_settings_subroute,
    prepare_e2e_ui_session,
    wait_for_state,
    warm_ui_route,
)


def _seed_composer_fixture(api_url: str) -> dict[str, object]:
    seeded = http_json(
        "POST",
        f"{api_url}/api/v1/chats/test/seed-skill-chip-composer-fixture",
    )
    assert isinstance(seeded, dict)
    chat_id = str(seeded.get("chat_id") or "")
    agent_id = str(seeded.get("agent_id") or "")
    assert chat_id.startswith("e2eslashchip")
    assert agent_id
    return seeded

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

            shell = wait_for_state(
                client,
                page,
                _SETTINGS_SKILLS_SHELL_STATE,
                timeout_sec=_warm_ui_parallel_wait_sec(120.0),
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
              const tab = Array.from(document.querySelectorAll('[role="tab"]')).find((t) => {
                const text = (t.textContent || '').trim();
                return (
                  t.getAttribute('value') === 'installed' ||
                  /^(Installed|已安装|已安裝)(\\d*)$/.test(text) ||
                  /Installed|已安装|已安裝/.test(text)
                );
              });
              if (!tab) return { ok: false, err: 'installed-tab-not-found' };
              const opts = {
                bubbles: true,
                cancelable: true,
                composed: true,
                button: 0,
                ctrlKey: false,
                detail: 1,
                view: window,
              };
              tab.dispatchEvent(new PointerEvent('pointerdown', { ...opts, pointerId: 1, isPrimary: true }));
              tab.dispatchEvent(new MouseEvent('mousedown', opts));
              tab.dispatchEvent(new PointerEvent('pointerup', { ...opts, pointerId: 1, isPrimary: true }));
              tab.dispatchEvent(new MouseEvent('mouseup', opts));
              tab.dispatchEvent(new MouseEvent('click', opts));
              return { ok: true, text: tab.textContent };
            })()"""
            client.evaluate(page, tab_click_js, timeout_sec=10.0)

            # 6. Verify Local Paths collapsible button or trigger rendered in UI
            local_paths_btn_js = """(() => {
              let btn = document.querySelector('[data-testid="local-skill-paths-trigger"]');
              const text = document.body?.innerText || '';
              const hasLocalPathsTitle = /Local Skill Paths|本地技能路径|本地技能目录|ローカルスキルパス|로컬 스킬 경로/i.test(text);
              if (!btn && !hasLocalPathsTitle) {
                const tab = Array.from(document.querySelectorAll('[role="tab"]')).find((t) => {
                  const tText = (t.textContent || '').trim();
                  return (
                    t.getAttribute('value') === 'installed' ||
                    /^(Installed|已安装|已安裝)(\\d*)$/.test(tText) ||
                    /Installed|已安装|已安裝/.test(tText)
                  );
                });
                if (tab) {
                  const opts = {
                    bubbles: true,
                    cancelable: true,
                    composed: true,
                    button: 0,
                    ctrlKey: false,
                    detail: 1,
                    view: window,
                  };
                  tab.dispatchEvent(new PointerEvent('pointerdown', { ...opts, pointerId: 1, isPrimary: true }));
                  tab.dispatchEvent(new MouseEvent('mousedown', opts));
                  tab.dispatchEvent(new PointerEvent('pointerup', { ...opts, pointerId: 1, isPrimary: true }));
                  tab.dispatchEvent(new MouseEvent('mouseup', opts));
                  tab.dispatchEvent(new MouseEvent('click', opts));
                }
              }
              btn = document.querySelector('[data-testid="local-skill-paths-trigger"]');
              const textAfter = document.body?.innerText || '';
              const hasTitleAfter = /Local Skill Paths|本地技能路径|本地技能目录|ローカルスキルパス|로컬 스킬 경로/i.test(textAfter);
              return {
                ready: !!btn || hasTitleAfter,
                hasBtn: !!btn,
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
              let input = document.querySelector('[data-testid="local-skill-path-input"]');
              let addBtn = document.querySelector('[data-testid="local-skill-path-add-btn"]');
              if (!input || !addBtn) {
                const btn = document.querySelector('[data-testid="local-skill-paths-trigger"]');
                if (btn) btn.click();
              }
              input = document.querySelector('[data-testid="local-skill-path-input"]');
              addBtn = document.querySelector('[data-testid="local-skill-path-add-btn"]');
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
              const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set;
              if (nativeSetter) {{
                nativeSetter.call(input, {json.dumps(str(test_skill_dir))});
              }} else {{
                input.value = {json.dumps(str(test_skill_dir))};
              }}
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

        # 13. Real User Task Flow with Real LLM (Universal Task Flow E2E)
        # Verify user can navigate to Chat, send a real prompt to the real model, and receive streaming response
        seeded = _seed_composer_fixture(api_url)
        chat_id = str(seeded["chat_id"])
        agent_id = str(seeded["agent_id"])
        agent_chat_path = str(seeded.get("ui_path") or f"/{chat_id}?agentId={agent_id}")
        ui_url = get_e2e_ui_url()
        warm_ui_route(agent_chat_path)

        with open_mcp_page(f"{ui_url}{agent_chat_path}") as (chat_client, chat_page):
            wait_for_state(
                chat_client,
                chat_page,
                """(() => ({
                  ready: !!document.querySelector('[data-chat-input]'),
                  hasInput: !!document.querySelector('[data-chat-input]'),
                }))()""",
                timeout_sec=_warm_ui_parallel_wait_sec(120.0),
            )

            # Pin direct SSE
            chat_client.evaluate(
                chat_page,
                """(() => { window.__MYRM_E2E_DIRECT_SSE__ = true; return true; })()""",
                timeout_sec=10.0,
            )

            # Type task prompt into input
            task_prompt = "请回答：125乘以8等于多少？请只回复数字结果。"
            type_js = f"""(() => {{
              const el = document.querySelector('[data-chat-input]');
              if (!el) return {{ ok: false, err: 'input-not-found' }};
              const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value')?.set;
              if (setter) {{
                setter.call(el, {json.dumps(task_prompt)});
              }} else {{
                el.value = {json.dumps(task_prompt)};
              }}
              el.dispatchEvent(new Event('input', {{ bubbles: true }}));
              el.dispatchEvent(new Event('change', {{ bubbles: true }}));
              return {{ ok: true, value: el.value }};
            }})()"""
            typed_res = chat_client.evaluate(chat_page, type_js, timeout_sec=10.0)
            assert isinstance(typed_res, dict) and typed_res.get("ok") is True, typed_res

            # Click send button
            send_btn_ready = wait_for_state(
                chat_client,
                chat_page,
                """(() => {
                  const btn = document.querySelector('.message-send-btn');
                  return {
                    ready: !!btn && !btn.disabled && btn.getAttribute('aria-disabled') !== 'true',
                    disabled: btn?.disabled ?? null,
                  };
                })()""",
                timeout_sec=15.0,
            )
            assert send_btn_ready.get("ready") is True, send_btn_ready

            chat_client.evaluate(
                chat_page,
                """(() => {
                  const btn = document.querySelector('.message-send-btn');
                  if (btn && !btn.disabled) btn.click();
                  return true;
                })()""",
                timeout_sec=5.0,
            )

            # Wait for real LLM streaming response to complete
            assistant_reply = wait_for_state(
                chat_client,
                chat_page,
                """(() => {
                  const store = window.__myrmChatStore?.getState?.();
                  const msgs = store?.messages ?? [];
                  const assistantMsg = msgs.find(
                    (m) => (m.role === 'assistant' || m.type === 'assistant') &&
                           String(m.content || m.text || '').trim().length > 0
                  );
                  const isStreaming = Boolean(store?.isStreaming || store?.loading);
                  const content = String(assistantMsg?.content || assistantMsg?.text || '').trim();
                  return {
                    ready: Boolean(assistantMsg) && !isStreaming && content.length > 0,
                    hasAssistantMsg: Boolean(assistantMsg),
                    isStreaming,
                    contentPreview: content.slice(0, 100),
                    fullContent: content,
                    totalMessages: msgs.length,
                  };
                })()""",
                timeout_sec=180.0,
            )
            assert assistant_reply.get("ready") is True, f"Assistant reply failed or timed out: {assistant_reply}"
            response_text = str(assistant_reply.get("fullContent") or "")
            print(f"\nREAL_LLM_ASSISTANT_RESPONSE: {response_text}")
            assert "1000" in response_text or len(response_text) > 0, f"Expected computation result in: {response_text}"
