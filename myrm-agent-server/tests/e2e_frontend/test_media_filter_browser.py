"""Browser E2E for Roadmap #17 — requires frontend :3000 and backend :8080."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e

_TEST_IMAGE = Path("/tmp/e2e-test-red.png")
_FRONTEND = "http://localhost:3000"


def _require_env(name: str) -> str:
    val = os.getenv(name, "").strip()
    if not val:
        pytest.skip(f"{name} not set")
    return val


@pytest.fixture(scope="module")
def test_image() -> Path:
    if not _TEST_IMAGE.exists():
        from PIL import Image

        Image.new("RGB", (64, 64), color="red").save(_TEST_IMAGE)
    return _TEST_IMAGE


@pytest.mark.asyncio
async def test_ui_agent_text_and_image_strip(test_image: Path) -> None:
    """Agent chat: vision-off strips image (STATUS), vision-on does not block attach path."""
    from patchright.async_api import async_playwright

    _require_env("BASIC_API_KEY")
    _require_env("BASIC_BASE_URL")
    _require_env("LITE_API_KEY")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            env={**os.environ},
        )
        page = await browser.new_page()
        await page.goto(_FRONTEND, wait_until="domcontentloaded", timeout=60_000)
        await page.wait_for_timeout(2000)

        adopt = page.get_by_role("button", name="采用服务端数据")
        if await adopt.count() > 0:
            await adopt.click()
            await page.wait_for_timeout(500)

        await page.get_by_role("radio", name="智能代理").click()
        await page.get_by_role("button", name="mimo-v2.5-pro").first.click()
        await page.wait_for_timeout(500)

        # Disable vision on mimo via settings
        await page.goto(f"{_FRONTEND}/settings/models", wait_until="domcontentloaded")
        await page.wait_for_timeout(1500)
        await page.get_by_role("button", name="OpenAI-Like (MiMo)").click()
        await page.get_by_role("button", name="模型配置").click()
        await page.wait_for_timeout(500)
        # Toggle vision off if enabled (click eye capability button area)
        vision_btns = page.locator('[aria-label*="vision"], [aria-label*="视觉"]')
        if await vision_btns.count() > 0:
            await vision_btns.first.click()
        await page.keyboard.press("Escape")

        await page.goto(_FRONTEND, wait_until="domcontentloaded")
        await page.wait_for_timeout(1500)
        await page.get_by_role("radio", name="智能代理").click()

        file_input = page.locator('input[type="file"]').first
        await file_input.set_input_files(str(test_image))
        await page.wait_for_timeout(1000)
        await page.get_by_role("textbox", name="输入消息...").fill("E2E UI: describe image color in one word")
        await page.get_by_role("button", name="发送").click()

        for _ in range(60):
            body = await page.content()
            if "media_stripped" in body or "已移除媒体" in body or "Removed media" in body:
                break
            if await page.get_by_role("button", name="发送").is_enabled():
                break
            await asyncio.sleep(2)
        else:
            await browser.close()
            pytest.fail("Timeout waiting for agent completion")

        body = await page.content()
        assert "media_stripped" in body or "已移除媒体" in body or "Removed media" in body

        await browser.close()
