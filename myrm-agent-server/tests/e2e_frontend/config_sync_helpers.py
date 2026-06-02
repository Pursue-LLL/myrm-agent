"""Shared helpers for config sync Playwright E2E tests."""

from playwright.async_api import Page

SETTINGS_PREFERENCES_URL = "http://localhost:3000/settings/preferences"

CONFLICT_DIALOG_TEXTS = ("Configuration Conflict Detected", "配置冲突检测")
KEEP_LOCAL_BUTTON_TEXTS = ("Keep Local Changes", "保留本地修改")
USE_SERVER_BUTTON_TEXTS = ("Use Server Version", "采用服务端版本", "采用服务端数据")


async def open_preferences(page: Page) -> None:
    await page.goto(SETTINGS_PREFERENCES_URL, timeout=60000)
    await page.wait_for_load_state("domcontentloaded", timeout=60000)
    await page.locator('[data-testid="config-enableCostEstimation"]').wait_for(
        state="visible", timeout=60000
    )


async def wait_for_conflict_dialog(page: Page) -> None:
    dialog = page.locator(
        f"text={CONFLICT_DIALOG_TEXTS[0]}"
    ).or_(page.locator(f"text={CONFLICT_DIALOG_TEXTS[1]}"))
    await dialog.first.wait_for(state="visible", timeout=15000)


async def click_keep_local(page: Page) -> None:
    btn = page.locator(
        f"button:has-text('{KEEP_LOCAL_BUTTON_TEXTS[0]}'), "
        f"button:has-text('{KEEP_LOCAL_BUTTON_TEXTS[1]}')"
    )
    await btn.click()


async def click_use_server(page: Page) -> None:
    btn = page.locator(
        ", ".join(f"button:has-text('{text}')" for text in USE_SERVER_BUTTON_TEXTS)
    )
    await btn.click()
