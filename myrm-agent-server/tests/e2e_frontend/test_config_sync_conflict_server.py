import asyncio
import logging
import uuid

from config_sync_helpers import (
    click_use_server,
    open_preferences,
    wait_for_conflict_dialog,
)
from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_config_sync_conflict_use_server():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        context_a = await browser.new_context()
        page_a = await context_a.new_page()

        context_b = await browser.new_context()
        page_b = await context_b.new_page()

        try:
            logger.info("Device A: Navigating to settings...")
            await open_preferences(page_a)

            logger.info("Device B: Navigating to settings...")
            await open_preferences(page_b)

            input_a = page_a.locator('[data-testid="config-systemInstructions"]')
            input_b = page_b.locator('[data-testid="config-systemInstructions"]')
            await input_a.wait_for(state="visible", timeout=60000)
            await input_b.wait_for(state="visible", timeout=60000)

            suffix = uuid.uuid4().hex[:8]
            val_a = f"Device A Instructions {suffix}"
            val_b = f"Device B Instructions {suffix}"

            logger.info("Device A: Modifying setting...")
            await input_a.fill(val_a)
            await input_a.blur()
            await asyncio.sleep(2.5)

            logger.info("Device B: Modifying the same setting to trigger conflict...")
            await input_b.fill(val_b)
            await input_b.blur()
            await asyncio.sleep(3)

            logger.info("Device B: Checking for conflict dialog...")
            await wait_for_conflict_dialog(page_b)

            await click_use_server(page_b)
            logger.info("Clicked Use Server")
            await asyncio.sleep(2)

            val = await input_b.input_value()
            assert val == val_a, f"Expected '{val_a}', got '{val}'"

            logger.info("Test completed successfully.")

        except Exception as e:
            logger.error(f"Test failed: {e}")
            raise
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(test_config_sync_conflict_use_server())
