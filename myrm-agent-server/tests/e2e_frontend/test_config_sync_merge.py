import asyncio
import logging

from config_sync_helpers import CONFLICT_DIALOG_TEXTS, open_preferences
from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_config_sync_merge():
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

            logger.info("Device A: Modifying setting A...")
            switch_a = page_a.locator('[data-testid="config-enableCostEstimation"]')
            initial_a = await switch_a.get_attribute("aria-checked")
            expected_a = "false" if initial_a == "true" else "true"
            await switch_a.click()

            await asyncio.sleep(2)

            logger.info("Device B: Modifying setting B to trigger silent merge...")
            switch_b = page_b.locator('[data-testid="config-enableWebNotifications"]')
            initial_b = await switch_b.get_attribute("aria-checked")
            expected_b = "false" if initial_b == "true" else "true"
            await switch_b.click()

            await asyncio.sleep(3)

            logger.info("Device B: Checking for conflict dialog (should be absent)...")
            dialog = page_b.locator(f"text={CONFLICT_DIALOG_TEXTS[0]}")
            if await dialog.count() == 0:
                dialog = page_b.locator(f"text={CONFLICT_DIALOG_TEXTS[1]}")
            assert not await dialog.is_visible(), "Conflict dialog should not appear for non-overlapping changes"

            logger.info("Device B: Verifying merged state in UI...")
            switch_a_on_b = page_b.locator('[data-testid="config-enableCostEstimation"]')
            is_checked_a = await switch_a_on_b.get_attribute("aria-checked")
            assert is_checked_a == expected_a, f"Device A's change was lost! Expected {expected_a}, got {is_checked_a}"

            switch_b_on_b = page_b.locator('[data-testid="config-enableWebNotifications"]')
            is_checked_b = await switch_b_on_b.get_attribute("aria-checked")
            assert is_checked_b == expected_b, f"Device B's change was lost! Expected {expected_b}, got {is_checked_b}"

            logger.info("Test completed successfully. 3-Way Merge worked silently.")

        except Exception as e:
            logger.error(f"Test failed: {e}")
            raise
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(test_config_sync_merge())
