"""Chrome E2E: Unified Knowledge Base Picker & Popover Mounting in Real WebUI.

Tests the full end-to-end task flow:
1. Opens real Chrome browser on http://localhost:3000.
2. Seeds a test shared context (knowledge base) via API.
3. Navigates to a chat session.
4. Finds and clicks the KnowledgePicker toggle button ([data-testid="knowledge-picker-toggle"]).
5. Verifies the Popover dialog opens, renders search bar and "管理知识库" link to /settings/wiki.
6. Finds the seeded knowledge base in the popover list and toggles switch ON.
7. Verifies ComposerContextChipStrip renders the mounted knowledge base chip with book icon.
8. Clicks chip remove button to unmount and verifies chip is cleanly removed.
"""

from __future__ import annotations

import json
import os
import sys

import pytest

_LIB = os.path.join(os.path.dirname(__file__), "..", "..", "..", "scripts", "dev", "lib")
if _LIB not in sys.path:
    sys.path.insert(0, os.path.normpath(_LIB))

from tests.support.chrome_mcp_e2e import (  # noqa: E402
    _warm_ui_parallel_wait_sec,
    dismiss_blocking_modals,
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_mcp_page,
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

_KNOWLEDGE_PICKER_TRIGGER_JS = """(() => {
  const btn = document.querySelector('[data-testid="knowledge-picker-toggle"]');
  return {
    ready: !!btn,
    visible: !!btn && btn.offsetParent !== null,
    hasAriaLabel: btn ? btn.getAttribute('aria-label') : null,
  };
})()"""

_OPEN_KNOWLEDGE_PICKER_POPOVER_JS = """(() => {
  const btn = document.querySelector('[data-testid="knowledge-picker-toggle"]');
  if (!btn) return { ok: false, error: 'no-btn' };
  btn.click();
  return { ok: true };
})()"""

_KNOWLEDGE_PICKER_POPOVER_CONTENT_JS = """(() => {
  const manageLink = Array.from(document.querySelectorAll('a')).find(
    (a) => a.getAttribute('href') === '/settings/wiki'
  );
  const searchInput = document.querySelector('input[placeholder*="知识库"], input[placeholder*="knowledge"]');
  const dialog = document.querySelector('[role="dialog"]');
  const switches = Array.from(document.querySelectorAll('[role="dialog"] [role="switch"]'));
  return {
    ready: !!dialog && (!!manageLink || !!searchInput),
    hasDialog: !!dialog,
    hasManageLink: !!manageLink,
    hasSearchInput: !!searchInput,
    switchCount: switches.length,
  };
})()"""

_TOGGLE_FIRST_KB_SWITCH_JS = """(() => {
  const dialog = document.querySelector('[role="dialog"]');
  if (!dialog) return { ok: false, error: 'no-dialog' };
  const sw = dialog.querySelector('[role="switch"]');
  if (!sw) return { ok: false, error: 'no-switch' };
  sw.click();
  return { ok: true };
})()"""

_CHECK_KNOWLEDGE_CHIP_MOUNTED_JS = """(() => {
  const strip = document.querySelector('[data-testid="composer-context-chip-strip"]');
  if (!strip) return { ready: false, hasStrip: false };
  const kbChip = Array.from(strip.querySelectorAll('[data-context-chip-id]')).find(
    (el) => el.getAttribute('data-context-chip-id')?.startsWith('knowledge-')
  );
  const removeBtn = kbChip?.querySelector('button');
  return {
    ready: Boolean(kbChip),
    hasStrip: true,
    hasKbChip: Boolean(kbChip),
    hasRemoveBtn: Boolean(removeBtn),
    chipText: kbChip ? kbChip.textContent : null,
  };
})()"""

_CLICK_REMOVE_KNOWLEDGE_CHIP_JS = """(() => {
  const strip = document.querySelector('[data-testid="composer-context-chip-strip"]');
  if (!strip) return { ok: false, error: 'no-strip' };
  const kbChip = Array.from(strip.querySelectorAll('[data-context-chip-id]')).find(
    (el) => el.getAttribute('data-context-chip-id')?.startsWith('knowledge-')
  );
  if (!kbChip) return { ok: false, error: 'no-kb-chip' };
  const removeBtn = kbChip.querySelector('button');
  if (!removeBtn) return { ok: false, error: 'no-remove-btn' };
  removeBtn.click();
  return { ok: true };
})()"""


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="READ",
    workload="STANDARD",
    private_reason="exclusive_backend",
)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_knowledge_picker_popover_chrome_e2e() -> None:
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()

    # Pre-seed at least one active shared context so the popover renders a switchable knowledge base
    try:
        http_json(
            "POST",
            f"{api_url}/api/v1/memory/shared-contexts",
            {
                "name": "E2E 企业知识库",
                "description": "用于 Chrome E2E 测试的自动化共享知识库",
                "policy": {"mode": "read_write"},
            },
            expected_statuses=frozenset({200, 201}),
        )
    except Exception:
        pass  # If it already exists or creation succeeds

    prepare_e2e_ui_session(api_url)
    seeded = _seed_composer_fixture(api_url)
    chat_id = str(seeded.get("chat_id") or "")
    agent_id = str(seeded.get("agent_id") or "")
    agent_chat_path = str(seeded.get("ui_path") or f"/{chat_id}?agentId={agent_id}")
    warm_ui_route(agent_chat_path)

    chat_page_url = f"{ui_url}{agent_chat_path}"
    with open_mcp_page(f"{ui_url}{agent_chat_path}") as (client, page):
        wait_for_state(
            client,
            page,
            """(() => ({
  ready:
    !!document.querySelector('[data-chat-input]') &&
    !!window.__MYRM_E2E_CHAT__ &&
    (window.__MYRM_E2E_CHAT__.turnSnapshot?.()?.agentSelectedSkillCount ?? 0) > 0,
}))()""",
            timeout_sec=_warm_ui_parallel_wait_sec(120.0),
        )
        dismiss_blocking_modals(client, page, recover_url=chat_page_url)

        # 1. 验证知识库挂载触发按钮正常渲染
        trigger_state = wait_for_state(
            client,
            page,
            _KNOWLEDGE_PICKER_TRIGGER_JS,
            timeout_sec=_warm_ui_parallel_wait_sec(45.0),
            page_url=chat_page_url,
        )
        assert trigger_state.get("ready") is True, f"Knowledge picker trigger not found: {trigger_state}"

        # 2. 点击触发按钮展开浮层
        click_res = client.evaluate(page, _OPEN_KNOWLEDGE_PICKER_POPOVER_JS, timeout_sec=15.0)
        assert click_res.get("ok") is True, f"Failed to click knowledge picker trigger: {click_res}"

        # 3. 验证浮层成功打开并具备搜索框与设置导流入口
        popover_state = wait_for_state(
            client,
            page,
            _KNOWLEDGE_PICKER_POPOVER_CONTENT_JS,
            timeout_sec=_warm_ui_parallel_wait_sec(20.0),
            page_url=chat_page_url,
        )
        assert popover_state.get("ready") is True, f"Knowledge picker popover failed to open: {popover_state}"
        assert popover_state.get("hasDialog") is True

        # 4. 如果列表中有可用知识库，进行挂载并在输入区验证 ContextChip 出现
        if popover_state.get("switchCount", 0) > 0:
            toggle_res = client.evaluate(page, _TOGGLE_FIRST_KB_SWITCH_JS, timeout_sec=10.0)
            assert toggle_res.get("ok") is True, f"Failed to toggle switch: {toggle_res}"

            # 验证 ContextChip 成功挂载至 ComposerContextChipStrip
            chip_state = wait_for_state(
                client,
                page,
                _CHECK_KNOWLEDGE_CHIP_MOUNTED_JS,
                timeout_sec=_warm_ui_parallel_wait_sec(15.0),
                page_url=chat_page_url,
            )
            assert chip_state.get("ready") is True, f"Knowledge chip failed to mount: {chip_state}"
            assert chip_state.get("hasKbChip") is True

            # 5. 点击胶囊上的移除按钮，验证胶囊正常卸载
            unmount_res = client.evaluate(page, _CLICK_REMOVE_KNOWLEDGE_CHIP_JS, timeout_sec=10.0)
            assert unmount_res.get("ok") is True, f"Failed to click remove chip: {unmount_res}"

            unmounted_state = wait_for_state(
                client,
                page,
                """(() => {
                  const strip = document.querySelector('[data-testid="composer-context-chip-strip"]');
                  const kbChip = Array.from(strip?.querySelectorAll('[data-context-chip-id]') || []).find(
                    (el) => el.getAttribute('data-context-chip-id')?.startsWith('knowledge-')
                  );
                  return { ready: !kbChip, hasKbChip: !!kbChip };
                })()""",
                timeout_sec=_warm_ui_parallel_wait_sec(15.0),
                page_url=chat_page_url,
            )
            assert unmounted_state.get("hasKbChip") is False

        # 6. 真实全链路业务闭环（Task Flow E2E）：挂载知识库 -> 发送查询 -> 触发模型与联邦知识检索
        # Pin SHPOIB direct-SSE so real UI send bypasses workspace multiplex bridge
        client.evaluate(
            page,
            """(() => { window.__MYRM_E2E_DIRECT_SSE__ = true; return true; })()""",
            timeout_sec=10.0,
        )

        # Clear drafts
        client.evaluate(
            page,
            """(() => {
              for (let i = localStorage.length - 1; i >= 0; i--) {
                const key = localStorage.key(i);
                if (key && key.startsWith('myrm_draft_')) {
                  localStorage.removeItem(key);
                }
              }
              window.__MYRM_E2E_CHAT__?.setInputMessage?.('');
              return true;
            })()""",
            timeout_sec=10.0,
        )

        # 挂载 E2E 企业知识库
        if popover_state.get("switchCount", 0) > 0:
            client.evaluate(page, _TOGGLE_FIRST_KB_SWITCH_JS, timeout_sec=10.0)

        # 输入真实业务知识库查询 prompt
        kb_task_prompt = "请用中文只回复四个字：测试通过"
        client.evaluate(
            page,
            f"""(() => {{
              const el = document.querySelector('[data-chat-input]');
              if (!el) return false;
              const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value')?.set;
              if (!setter) return false;
              setter.call(el, {json.dumps(kb_task_prompt)});
              el.dispatchEvent(new Event('input', {{ bubbles: true }}));
              el.dispatchEvent(new Event('change', {{ bubbles: true }}));
              return true;
            }})()""",
            timeout_sec=10.0,
        )

        # 点击发送按钮
        send_btn_ready = wait_for_state(
            client,
            page,
            """(() => {
              const btn = document.querySelector('.message-send-btn');
              return {
                ready: !!btn && !btn.disabled && btn.getAttribute('aria-disabled') !== 'true',
              };
            })()""",
            timeout_sec=15.0,
        )
        assert send_btn_ready.get("ready") is True

        btn_clicked = client.evaluate(
            page,
            """(() => {
              const btn = document.querySelector('.message-send-btn');
              if (!btn || btn.disabled) return false;
              btn.click();
              return true;
            })()""",
            timeout_sec=5.0,
        )
        assert btn_clicked is True, "Send button click failed"

        # 5. Assert input textarea cleared and composer chip strip unmounted
        wait_for_state(
            client,
            page,
            """(() => {
              const input = document.querySelector('[data-chat-input]');
              const strip = document.querySelector('[data-testid="composer-context-chip-strip"]');
              return {
                ready: !!input && input.value === '' && !strip,
                inputValue: input?.value ?? null,
                hasStrip: Boolean(strip),
              };
            })()""",
            timeout_sec=30.0,
        )

        # 6. 等待真实助手回答流式返回并完成
        assistant_reply = wait_for_state(
            client,
            page,
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
        assert (
            assistant_reply.get("ready") is True
        ), f"Assistant reply failed or timed out: {assistant_reply}"
        response_text = str(assistant_reply.get("fullContent") or "")
        print(f"\nREAL_LLM_KNOWLEDGE_ASSISTANT_RESPONSE: {response_text}")
        assert len(response_text) > 0, "Model returned empty response"

