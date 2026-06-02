import os

import pytest
from patchright.async_api import async_playwright


@pytest.mark.asyncio
async def test_i18n_personality_command():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            # Set locale to zh-CN to test localization
            context = await browser.new_context(locale="zh-CN")
            page = await context.new_page()

            frontend_url = os.environ.get("FRONTEND_URL", "http://127.0.0.1:3000/")
            print(f"Navigating to {frontend_url}...")
            await page.goto(frontend_url, timeout=60000)
            await page.wait_for_timeout(2000)

            print("Finding chat input...")
            # Wait for textarea
            chat_input = page.locator(
                'textarea[placeholder*="发送消息"], textarea[placeholder*="Message"], [data-testid="chat-input"]'
            ).first
            if not await chat_input.is_visible():
                chat_input = page.locator("textarea").first

            await chat_input.wait_for(state="visible", timeout=30_000)

            print("Sending /personality command...")
            await chat_input.fill("/personality")

            # Find and click send button
            send = page.locator('button[aria-label="发送"], button[aria-label="Send"]')
            if await send.is_visible():
                await send.click()
            else:
                await chat_input.press("Enter")

            print("Waiting for response...")
            # Wait for the response to appear
            # We look for typical translated strings for personality: "当前设定的人设为" or "当前性格风格为"
            # Or English fallback: "Personality style is"
            try:
                await page.wait_for_function(
                    """() => {
                        const text = document.body.innerText;
                        return text.includes('当前设定') || text.includes('当前性格') || text.includes('当前人设') || text.includes('Personality') || text.includes('当前');
                    }""",
                    timeout=30_000,
                )
                print("✅ Found localized response for /personality")
                passed = True
            except Exception as e:
                print(f"❌ Failed to find localized response: {e}")
                passed = False
                await page.screenshot(path="i18n_test_failed.png")
                html_content = await page.content()
                with open("i18n_test_failed.html", "w", encoding="utf-8") as f:
                    f.write(html_content)

            assert passed, "Failed to get a localized response from the backend."

        finally:
            await browser.close()
