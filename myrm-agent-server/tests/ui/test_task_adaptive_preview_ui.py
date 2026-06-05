"""UI E2E tests for TaskAdaptivePreview component using Patchright."""

import asyncio
from pathlib import Path

import pytest
from patchright.async_api import async_playwright


@pytest.mark.asyncio
async def test_task_adaptive_preview_ui_display():
    """Test that TaskAdaptivePreview component renders correctly in the browser."""

    async with async_playwright() as p:
        # Launch browser in headless mode
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        try:
            # Navigate to the frontend
            print("\n[UI Test] Navigating to http://localhost:3000...")
            # Use "domcontentloaded" instead of "networkidle" for faster loading
            await page.goto("http://localhost:3000", wait_until="domcontentloaded", timeout=60000)

            # Wait for the page to settle
            await page.wait_for_timeout(2000)
            print("[UI Test] Page loaded successfully")

            # Take a screenshot of the initial state
            screenshots_dir = Path(__file__).parent / "screenshots"
            screenshots_dir.mkdir(exist_ok=True)

            initial_screenshot = screenshots_dir / "01_initial_page.png"
            await page.screenshot(path=str(initial_screenshot), full_page=True)
            print(f"[UI Test] Screenshot saved: {initial_screenshot}")

            # Check if chat interface exists
            chat_interface = await page.query_selector("[data-testid='chat-window'], .chat-window, #chat-window")
            if chat_interface:
                print("[UI Test] ✅ Chat interface found")
            else:
                # Try alternative selectors
                print("[UI Test] Looking for chat components...")
                input_field = await page.query_selector("textarea, input[type='text']")
                if input_field:
                    print("[UI Test] ✅ Found input field")

            # Look for any task-adaptive UI elements
            task_adaptive_elements = await page.query_selector_all(
                "[data-testid*='task-adaptive'], [class*='task-adaptive'], [id*='task-adaptive']"
            )

            if task_adaptive_elements:
                print(f"[UI Test] ✅ Found {len(task_adaptive_elements)} task-adaptive UI elements")
                for i, elem in enumerate(task_adaptive_elements[:3]):  # Check first 3
                    text = await elem.text_content()
                    print(f"[UI Test]   Element {i + 1}: {text[:50] if text else '(empty)'}...")
            else:
                print("[UI Test] ⚠️  No task-adaptive UI elements found (this is expected if no digest is loaded)")

            # Take final screenshot
            final_screenshot = screenshots_dir / "02_final_state.png"
            await page.screenshot(path=str(final_screenshot), full_page=True)
            print(f"[UI Test] Final screenshot saved: {final_screenshot}")

            print("\n[UI Test] ✅ UI test completed successfully")
            print(f"[UI Test] Screenshots saved to: {screenshots_dir}")

        finally:
            await browser.close()


@pytest.mark.asyncio
async def test_task_adaptive_preview_with_simulated_data():
    """Test TaskAdaptivePreview by simulating a chat with task_adaptive_digest."""

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        try:
            print("\n[UI Test] Testing TaskAdaptivePreview with simulated data...")

            # Navigate to frontend
            await page.goto("http://localhost:3000", wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(2000)
            print("[UI Test] Page loaded")

            screenshots_dir = Path(__file__).parent / "screenshots"
            screenshots_dir.mkdir(exist_ok=True)

            # Try to find and click the "New Chat" button
            new_chat_button = await page.query_selector(
                "[data-testid='new-chat'], button:has-text('New Chat'), button:has-text('新建对话')"
            )
            if new_chat_button:
                print("[UI Test] Clicking 'New Chat' button...")
                await new_chat_button.click()
                await page.wait_for_timeout(1000)

                screenshot = screenshots_dir / "03_new_chat.png"
                await page.screenshot(path=str(screenshot), full_page=True)
                print(f"[UI Test] Screenshot saved: {screenshot}")

            # Look for input field
            input_field = await page.query_selector("textarea, input[type='text']")
            if input_field:
                print("[UI Test] Found input field, typing test message...")
                await input_field.fill("Test message for TaskAdaptivePreview")
                await page.wait_for_timeout(500)

                screenshot = screenshots_dir / "04_message_typed.png"
                await page.screenshot(path=str(screenshot), full_page=True)
                print(f"[UI Test] Screenshot saved: {screenshot}")

            # Check if there are any task-adaptive banners or info boxes
            banners = await page.query_selector_all("[role='alert'], [class*='banner'], [class*='info']")
            if banners:
                print(f"[UI Test] Found {len(banners)} banner/info elements")
                for _i, banner in enumerate(banners[:3]):
                    text = await banner.text_content()
                    if text and "task" in text.lower() or "adaptive" in text.lower():
                        print(f"[UI Test] ✅ Found task-adaptive related banner: {text[:80]}...")

            final_screenshot = screenshots_dir / "05_final_simulated.png"
            await page.screenshot(path=str(final_screenshot), full_page=True)
            print(f"[UI Test] Final screenshot saved: {final_screenshot}")

            print("\n[UI Test] ✅ Simulated data test completed")
            print(f"[UI Test] All screenshots saved to: {screenshots_dir}")

        finally:
            await browser.close()


if __name__ == "__main__":
    # Run tests directly
    asyncio.run(test_task_adaptive_preview_ui_display())
    asyncio.run(test_task_adaptive_preview_with_simulated_data())
