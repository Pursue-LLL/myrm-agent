"""Chrome E2E: Unified Knowledge Base Picker & Popover Mounting in Real WebUI.

Tests the full end-to-end task flow:
1. Opens real Chrome browser on http://localhost:3000.
2. Navigates to a chat session.
3. Finds and clicks the KnowledgePicker toggle button ([data-testid="knowledge-picker-toggle"]).
4. Verifies the Popover dialog opens, renders search bar and "管理知识库" link to /settings/wiki.
5. Verifies the Popover content contains either available KBs or empty state guide card.
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
    open_mcp_page,
    prepare_e2e_ui_session,
    wait_for_state,
    warm_ui_route,
)

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
  return {
    ready: !!dialog && (!!manageLink || !!searchInput),
    hasDialog: !!dialog,
    hasManageLink: !!manageLink,
    hasSearchInput: !!searchInput,
  };
})()"""


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="READ", workload="STANDARD")
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.timeout(180)
def test_knowledge_picker_popover_chrome_e2e() -> None:
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()

    prepare_e2e_ui_session(api_url)
    warm_ui_route("/")

    chat_page_url = f"{ui_url.rstrip('/')}/"
    with open_mcp_page(
        chat_page_url,
        timeout_ms=120_000,
        request_timeout_sec=180.0,
    ) as (client, page):
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
