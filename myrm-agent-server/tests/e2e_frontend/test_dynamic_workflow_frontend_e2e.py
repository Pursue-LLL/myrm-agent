"""Frontend E2E — Dynamic Workflow toggle UI (send flow covered by API e2e)."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import httpx
import pytest

_SERVER_ROOT = Path(__file__).resolve().parents[2]
if str(_SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(_SERVER_ROOT))

from patchright.async_api import async_playwright  # noqa: E402

from tests.e2e_frontend.verifier_helpers import (  # noqa: E402
    BACKEND_BASE,
    FRONTEND_BASE,
    select_chat_model,
    sync_providers_from_env,
)


async def _clear_pending_approvals() -> None:
    async with httpx.AsyncClient(base_url=BACKEND_BASE, timeout=30.0) as client:
        response = await client.get("/api/v1/approvals")
        response.raise_for_status()
        approvals = response.json().get("approvals", [])
        ids = [item["id"] for item in approvals if isinstance(item, dict) and item.get("id")]
        if not ids:
            return
        batch = await client.post(
            "/api/v1/approvals/batch-resolve",
            json={"approval_ids": ids, "decision": "deny"},
        )
        batch.raise_for_status()


async def _find_visible_workflow_toggle(page):
    buttons = page.locator(
        'button[aria-label="动态工作流模式"], button[aria-label="Dynamic Workflow Mode"]'
    )
    await buttons.first.wait_for(state="attached", timeout=60000)
    for index in range(await buttons.count()):
        candidate = buttons.nth(index)
        if await candidate.is_visible():
            return candidate
    raise RuntimeError("Workflow toggle exists in DOM but none are visible")


async def run_workflow_toggle_ui_e2e() -> None:
    os.environ.setdefault(
        "PLAYWRIGHT_BROWSERS_PATH",
        "/Users/yululiu/Library/Caches/ms-playwright",
    )
    await sync_providers_from_env()
    await _clear_pending_approvals()

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True, env={**os.environ})
        context = await browser.new_context(viewport={"width": 1280, "height": 800})
        page = await context.new_page()

        await page.goto(f"{FRONTEND_BASE}/", timeout=60000, wait_until="domcontentloaded")
        await page.wait_for_timeout(1500)
        await select_chat_model(page)

        toggle = await _find_visible_workflow_toggle(page)
        assert await toggle.get_attribute("aria-pressed") == "false"

        await toggle.click()
        assert await toggle.get_attribute("aria-pressed") == "true"

        await toggle.click()
        assert await toggle.get_attribute("aria-pressed") == "false"

        await browser.close()


@pytest.mark.timeout(120)
def test_dynamic_workflow_toggle_ui_e2e() -> None:
    asyncio.run(run_workflow_toggle_ui_e2e())
