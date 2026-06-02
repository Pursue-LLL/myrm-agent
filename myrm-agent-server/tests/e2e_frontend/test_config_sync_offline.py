import asyncio
import logging
import uuid

from config_sync_helpers import open_preferences
from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_config_sync_offline():
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

            offline_value = f"Offline Instructions E2E {uuid.uuid4().hex[:8]}"

            logger.info("Device A: Going offline...")
            await context_a.set_offline(True)

            logger.info("Device A: Modifying setting while offline...")
            await input_a.fill(offline_value)
            await input_a.blur()

            await asyncio.sleep(2)

            logger.info("Device B: Checking setting (should NOT be synced yet)...")
            val_b = await input_b.input_value()
            assert val_b != offline_value, "Change synced while offline?!"

            logger.info("Device A: Going online...")
            await context_a.set_offline(False)

            await asyncio.sleep(4)

            logger.info("Device A: Reloading to verify persistence after offline queue flush...")
            await page_a.goto("http://localhost:3000/settings/preferences", timeout=60000, wait_until="domcontentloaded")

            input_a_reloaded = page_a.locator('[data-testid="config-systemInstructions"]')
            await input_a_reloaded.wait_for(state="visible", timeout=60000)
            val_a = await input_a_reloaded.input_value()
            assert val_a == offline_value, f"Offline change not persisted! Got: {val_a}"

            logger.info("Device B: Reloading to verify server sync propagated...")
            await page_b.goto("http://localhost:3000/settings/preferences", timeout=60000, wait_until="domcontentloaded")
            input_b_reloaded = page_b.locator('[data-testid="config-systemInstructions"]')
            await input_b_reloaded.wait_for(state="visible", timeout=60000)
            val_b_after = await input_b_reloaded.input_value()
            assert val_b_after == offline_value, (
                f"Change not synced to server after coming online! Got: {val_b_after}"
            )

            logger.info("Test completed successfully. Offline queueing worked.")

        except Exception as e:
            logger.error(f"Test failed: {e}")
            raise
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(test_config_sync_offline())
