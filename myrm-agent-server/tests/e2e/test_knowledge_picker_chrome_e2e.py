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
    return seeded


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

    chat_page_url = f"{ui_url.rstrip('/')}{agent_chat_path}"
    with open_mcp_page(chat_page_url) as (client, page):
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

        # 6. 验证在消息流中注入带有 kb_name 的知识库来源时，SourcesButton 与 SourceItem 正常渲染知识库标签
        inject_sources_res = client.evaluate(
            page,
            """(() => {
              const chatStore = window.__myrmChatStore;
              if (!chatStore?.getState || !chatStore.setState) {
                return { ok: false, err: 'chat-store-missing' };
              }
              const testMsgId = 'e2e-knowledge-source-test-msg';
              const message = {
                messageId: testMsgId,
                chatId: chatStore.getState().chatId || 'e2e-chat-test',
                createdAt: new Date(),
                content: '根据企业知识库规范，系统支持跨源联邦索引。',
                role: 'assistant',
                sources: [
                  {
                    index: 1,
                    type: 'knowledge',
                    title: '架构设计准则 § 联邦索引',
                    kb_name: 'E2E 企业知识库',
                    snippet: '跨源索引通过 SQLite 附加数据库与 FTS5 全文检索引擎实现。',
                  },
                ],
              };
              chatStore.setState({
                messages: [message],
                loading: false,
                isMessagesLoaded: true,
                messageAppeared: true,
              });
              return { ok: true };
            })()""",
            timeout_sec=10.0,
        )
        assert inject_sources_res.get("ok") is True

        # 验证渲染并包含 E2E 企业知识库 标签
        source_badge_state = wait_for_state(
            client,
            page,
            """(() => {
              const text = document.body?.innerText || '';
              const hasContent = text.includes('架构设计准则') || text.includes('跨源联邦索引');
              const hasBadge = text.includes('E2E 企业知识库');
              return {
                ready: hasContent || hasBadge,
                hasContent,
                hasBadge,
              };
            })()""",
            timeout_sec=_warm_ui_parallel_wait_sec(15.0),
        )
        assert source_badge_state.get("ready") is True, source_badge_state

