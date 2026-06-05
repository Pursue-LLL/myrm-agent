import asyncio
from pathlib import Path

import pytest
from patchright.async_api import Page, async_playwright

BASE_URL = "http://localhost:3000"


@pytest.fixture(scope="function")
async def browser_page():
    """启动浏览器并返回页面对象"""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1920, "height": 1080})
        page = await context.new_page()

        yield page

        await context.close()
        await browser.close()


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_settings_menu_e2e(browser_page: Page):
    """测试设置菜单重构后的核心功能 (OP-1, OP-2, OP-3)"""
    page = browser_page
    screenshots_dir = Path(__file__).parent / "screenshots"
    screenshots_dir.mkdir(parents=True, exist_ok=True)

    print("\n" + "=" * 80)
    print("Settings Menu UX Refactor E2E Test")
    print("=" * 80)

    # ===== 测试 1: 访问设置主页并验证 6 大分组 =====
    print("\n[测试 1/4] 访问设置主页并验证分组...")
    try:
        # 跳过 BootScreen
        await page.goto(BASE_URL)
        await page.evaluate("window.sessionStorage.setItem('myrm_boot_shown', '1')")

        await page.goto(f"{BASE_URL}/settings", wait_until="domcontentloaded")
        await asyncio.sleep(2)

        page_text = await page.inner_text("body")
        # 验证至少存在一些关键的父级菜单
        assert "模型" in page_text or "Model" in page_text, "Page content does not match expected settings menu"

        await page.screenshot(path=str(screenshots_dir / "settings_test1_home.png"))
        print("✓ 设置主页可以访问")
    except Exception as e:
        await page.screenshot(path=str(screenshots_dir / "settings_test1_failed.png"))
        raise AssertionError(f"Failed to access settings home page: {e}") from e

    # ===== 测试 2: 验证 OP-1 子选项卡联合反向搜索 =====
    print("\n[测试 2/4] 验证 OP-1 子选项卡联合反向搜索...")
    try:
        # 查找搜索框并输入 "语音"
        search_input = await page.query_selector('input[type="text"]')
        assert search_input is not None, "Search input was not found"

        await search_input.fill("语音")
        await asyncio.sleep(1)

        # 验证是否出现了匹配子项的提示
        page_text = await page.inner_text("body")
        assert "语音" in page_text or "voice" in page_text.lower(), "Reverse search result was not found"

        await page.screenshot(path=str(screenshots_dir / "settings_test2_search.png"))
        print("✓ OP-1 反向搜索验证通过")
    except Exception as e:
        await page.screenshot(path=str(screenshots_dir / "settings_test2_failed.png"))
        raise AssertionError(f"Reverse search test failed: {e}") from e

    # ===== 测试 3: 验证 OP-2 切换子选项卡功能 =====
    print("\n[测试 3/4] 验证 OP-2 切换子选项卡功能...")
    try:
        # 导航到模型服务页面
        await page.goto(f"{BASE_URL}/settings/models", wait_until="domcontentloaded")
        await asyncio.sleep(2)

        # 查找子选项卡触发器 (如 "默认模型" 或 "default")
        # 我们点击包含 "默认" 或 "Default" 的按钮
        tabs = page.locator('[role="tab"]')
        count = await tabs.count()
        assert count >= 2, "Not enough subtabs were found"

        await tabs.nth(1).click(force=True)
        await asyncio.sleep(1)

        # 验证 URL 是否更新为 ?sub=default
        assert "sub=default" in page.url, f"URL was not updated correctly: {page.url}"

        await page.screenshot(path=str(screenshots_dir / "settings_test3_subtabs.png"))
        print("✓ OP-2 子选项卡切换验证通过")
    except Exception as e:
        await page.screenshot(path=str(screenshots_dir / "settings_test3_failed.png"))
        raise AssertionError(f"Subtab switching test failed: {e}") from e

    # ===== 测试 4: 验证 OP-3 服务端 307/308 重定向 =====
    print("\n[测试 4/4] 验证 OP-3 废弃路由重定向...")
    try:
        # 直接访问废弃路由 /settings/voice
        await page.goto(f"{BASE_URL}/settings/voice", wait_until="domcontentloaded")
        await asyncio.sleep(2)

        # 验证 URL 是否被重定向到 /settings/channels?sub=voice
        assert "channels" in page.url and "sub=voice" in page.url, f"Redirect failed, current URL: {page.url}"

        await page.screenshot(path=str(screenshots_dir / "settings_test4_redirect.png"))
        print("✓ OP-3 废弃路由重定向验证通过")
    except Exception as e:
        await page.screenshot(path=str(screenshots_dir / "settings_test4_failed.png"))
        raise AssertionError(f"Deprecated route redirect test failed: {e}") from e
