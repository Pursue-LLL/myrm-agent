"""Playwright E2E: teammate P2P messages in SubagentDashboard (SSE + API refresh)."""

from __future__ import annotations

import json

import pytest
from patchright.async_api import Page, async_playwright

pytestmark = pytest.mark.e2e

CHAT_ID = "teammate-ui-e2e-chat"
TASK_A = "worker-a"
TASK_B = "worker-b"
MESSAGE_BODY = "E2E teammate ping from mailbox"
MESSAGE_ID = "teammate-e2e-msg-1"


@pytest.fixture(scope="function")
async def browser_page() -> Page:
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1280, "height": 900})
        page = await context.new_page()
        yield page
        await context.close()
        await browser.close()


def _subagents_payload() -> dict[str, object]:
    row = {
        "message_id": MESSAGE_ID,
        "from_task_id": TASK_A,
        "to_task_id": TASK_B,
        "from_agent_type": "coder",
        "body": MESSAGE_BODY,
        "created_at": 500.0,
    }
    return {
        "success": True,
        "data": [
            {
                "task_id": TASK_A,
                "agent_type": "coder",
                "status": "running",
                "progress": 40,
                "teammate_messages": [row],
            },
            {
                "task_id": TASK_B,
                "agent_type": "researcher",
                "status": "running",
                "progress": 55,
                "teammate_messages": [row],
            },
        ],
    }


def _tree_seed() -> list[dict[str, object]]:
    row = {
        "message_id": MESSAGE_ID,
        "from_task_id": TASK_A,
        "to_task_id": TASK_B,
        "from_agent_type": "coder",
        "body": MESSAGE_BODY,
        "created_at": 500.0,
    }
    return [
        {
            "task_id": TASK_A,
            "parent_task_id": "",
            "agent_type": "coder",
            "description": "coder worker",
            "status": "running",
            "progress": 40,
            "teammate_messages": [row],
        },
        {
            "task_id": TASK_B,
            "parent_task_id": "",
            "agent_type": "researcher",
            "description": "research worker",
            "status": "running",
            "progress": 55,
            "teammate_messages": [row],
        },
    ]


async def _mock_chat_routes(page: Page) -> None:
    async def handle_chat(route) -> None:
        url = route.request.url
        if "/subagents" in url:
            await route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(_subagents_payload()),
            )
            return
        if "/messages" in url:
            await route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(
                    {
                        "success": True,
                        "data": {
                            "messages": [],
                            "has_more": False,
                            "next_cursor": None,
                        },
                    }
                ),
            )
            return
        await route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "success": True,
                    "data": {
                        "chat": {
                            "id": CHAT_ID,
                            "title": "Teammate E2E",
                            "actionMode": "agent",
                            "compacted_summary": None,
                            "compacted_before_id": None,
                            "workspace_dir": None,
                            "created_at": "2026-01-01T00:00:00Z",
                            "updated_at": "2026-01-01T00:00:00Z",
                        },
                        "message_count": 0,
                    },
                }
            ),
        )

    await page.route(f"**/chats/{CHAT_ID}**", handle_chat)


async def _seed_subagent_tree(page: Page) -> None:
    await page.evaluate(
        """([chatId, tree]) => {
          const store = window.__myrmSubagentStore;
          if (store) {
            store.getState().setNodes(tree);
          }
          window.dispatchEvent(
            new CustomEvent('subagents_updated', {
              detail: { chat_id: chatId, tree },
            }),
          );
        }""",
        [CHAT_ID, _tree_seed()],
    )


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_teammate_mailbox_dashboard_sse_and_refresh(
    browser_page: Page,
    ephemeral_frontend: str,
) -> None:
    """Panel shows mailbox text; SSE append works; reopening dashboard re-fetches hydrated API rows."""
    page = browser_page
    await _mock_chat_routes(page)

    await page.goto(f"{ephemeral_frontend}/{CHAT_ID}", wait_until="domcontentloaded")
    await page.wait_for_selector("textarea", timeout=20_000)
    await page.wait_for_function("() => !!window.__myrmSubagentStore", timeout=30_000)
    await _seed_subagent_tree(page)
    await page.wait_for_function(
        "() => Object.keys(window.__myrmSubagentStore.getState().nodes || {}).length > 0",
        timeout=10_000,
    )

    trigger = page.get_by_test_id("subagent-dashboard-trigger")
    await trigger.wait_for(state="visible", timeout=10_000)
    await trigger.click()

    title = page.get_by_text("Teammate messages").or_(page.get_by_text("队友私信"))
    await title.first.wait_for(state="visible", timeout=10_000)
    await page.get_by_text(MESSAGE_BODY).first.wait_for(state="visible", timeout=10_000)

    sse_body = "E2E teammate live via SSE"
    await page.evaluate(
        """([chatId, msg]) => {
          window.dispatchEvent(
            new CustomEvent('teammate_message', {
              detail: { chat_id: chatId, message: msg },
            }),
          );
        }""",
        [
            CHAT_ID,
            {
                "message_id": "teammate-e2e-msg-2",
                "from_task_id": TASK_A,
                "to_task_id": TASK_B,
                "body": sse_body,
                "created_at": 600,
            },
        ],
    )
    await page.get_by_text(sse_body).first.wait_for(state="visible", timeout=10_000)

    await page.keyboard.press("Escape")
    await trigger.click()
    await page.get_by_text(MESSAGE_BODY).first.wait_for(state="visible", timeout=10_000)
    await page.get_by_text(sse_body).first.wait_for(state="visible", timeout=10_000)
