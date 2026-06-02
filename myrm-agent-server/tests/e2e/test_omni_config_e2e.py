import asyncio
from pathlib import Path

import pytest
from dotenv import load_dotenv
from patchright.async_api import Page, async_playwright

load_dotenv(override=True)

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
async def test_omni_config_e2e(browser_page: Page):
    """测试 Omni-Config Phase 1 (SchemaForm) 和 Phase 2 (Time Machine)"""
    page = browser_page
    screenshots_dir = Path(__file__).parent / "screenshots"
    screenshots_dir.mkdir(parents=True, exist_ok=True)

    print("\n" + "=" * 80)
    print("Omni-Config E2E Test")
    print("=" * 80)

    # ===== 测试 1: 访问偏好设置页面并验证 SchemaForm =====
    print("\n[测试 1/3] 访问偏好设置页面并验证 SchemaForm...")
    try:
        # 跳过 BootScreen
        await page.goto(BASE_URL)
        await page.evaluate("window.sessionStorage.setItem('myrm_boot_shown', '1')")

        await page.goto(f"{BASE_URL}/settings/preferences", wait_until="domcontentloaded")
        await asyncio.sleep(2)

        # 查找 "获取原始网页" (Fetch Raw Webpage) 的 Switch
        # SchemaForm 会根据 schema 渲染标题和描述
        page_text = await page.inner_text("body")
        assert "抓取原始网页" in page_text or "获取原始网页" in page_text or "Fetch Raw Webpage" in page_text, "SchemaForm did not render expected properties"

        await page.screenshot(path=str(screenshots_dir / "omni_test1_schemaform.png"))
        print("✓ SchemaForm 渲染验证通过")
    except Exception as e:
        await page.screenshot(path=str(screenshots_dir / "omni_test1_failed.png"))
        raise AssertionError(f"Failed to verify SchemaForm: {e}") from e

    # ===== 测试 2: 主动修改配置以产生历史记录 =====
    print("\n[测试 2/4] 主动修改配置以产生历史记录...")
    try:
        # 找到 "抓取原始网页" 的开关
        # 由于是 SchemaForm 渲染，我们可以通过 label 找到对应的 switch
        cost_estimation_label = page.locator('label', has_text="抓取原始网页")
        if await cost_estimation_label.count() == 0:
            cost_estimation_label = page.locator('label', has_text="Fetch Raw Webpage")

        # 找到包含该 label 的整行，然后找到其中的 switch button
        row_locator = page.locator('div.flex.items-start.justify-between', has=cost_estimation_label)
        switch_btn = row_locator.locator('button[role="switch"]')

        # 获取初始状态
        initial_state = await switch_btn.get_attribute("aria-checked")
        print(f"  - 初始状态: {initial_state}")

        # 点击切换状态
        await switch_btn.click()
        await asyncio.sleep(2) # 等待自动保存

        # 获取修改后的状态
        new_state = await switch_btn.get_attribute("aria-checked")
        print(f"  - 修改后状态: {new_state}")
        assert initial_state != new_state, "Switch state did not change after click"

        await page.screenshot(path=str(screenshots_dir / "omni_test2_modified.png"))
        print("✓ 配置修改验证通过")
    except Exception as e:
        await page.screenshot(path=str(screenshots_dir / "omni_test2_failed.png"))
        raise AssertionError(f"Failed to modify config: {e}") from e

    # ===== 测试 3: 验证时光机弹窗 =====
    print("\n[测试 3/4] 验证时光机弹窗...")
    try:
        # 查找并点击 "时光机" 按钮
        time_machine_btn = page.locator('button:has-text("时光机")')
        if await time_machine_btn.count() == 0:
            time_machine_btn = page.locator('button:has-text("Time Machine")')

        await time_machine_btn.click()
        await asyncio.sleep(2)

        # 验证弹窗是否打开，且包含历史记录
        dialog_text = await page.inner_text('[role="dialog"]')
        assert "配置时光机" in dialog_text or "Time Machine" in dialog_text, "Time Machine dialog did not open"

        # 验证是否显示了 "当前版本" 和 "恢复此版本"
        assert "当前版本" in dialog_text or "恢复此版本" in dialog_text, "History records not found in dialog"

        await page.screenshot(path=str(screenshots_dir / "omni_test3_timemachine.png"))
        print("✓ 时光机弹窗验证通过")
    except Exception as e:
        await page.screenshot(path=str(screenshots_dir / "omni_test3_failed.png"))
        raise AssertionError(f"Time Machine dialog test failed: {e}") from e

    # ===== 测试 4: 验证时光机回滚及 UI 状态更新 =====
    print("\n[测试 4/4] 验证时光机回滚及 UI 状态更新...")
    try:
        # 查找 "恢复此版本" 按钮并点击第一个 (恢复到上一个版本)
        restore_btns = page.locator('button:has-text("恢复此版本")')
        if await restore_btns.count() == 0:
            restore_btns = page.locator('button:has-text("Restore")')

        count = await restore_btns.count()
        assert count > 0, "No history records available to restore"

        await restore_btns.nth(0).click()
        await asyncio.sleep(2)

        # 验证 Toast 提示
        page_text = await page.inner_text("body")
        assert "Successfully restored" in page_text or "恢复" in page_text, "Rollback success toast not found"

        # 关闭弹窗 (如果点击恢复后没有自动关闭)
        close_btn = page.locator('[role="dialog"] button[aria-label="Close"]')
        if await close_btn.count() > 0:
            await close_btn.click()
            await asyncio.sleep(1)

        # 重新获取开关状态，验证是否回滚到初始状态
        cost_estimation_label = page.locator('label', has_text="抓取原始网页")
        if await cost_estimation_label.count() == 0:
            cost_estimation_label = page.locator('label', has_text="Fetch Raw Webpage")
            
        row_locator = page.locator('div.flex.items-start.justify-between', has=cost_estimation_label)
        switch_btn = row_locator.locator('button[role="switch"]')
        restored_state = await switch_btn.get_attribute("aria-checked")
        print(f"  - 回滚后状态: {restored_state}")

        assert restored_state == initial_state, f"State did not rollback! Expected {initial_state}, got {restored_state}"
        print("✓ 时光机回滚及 UI 状态更新验证通过")

        await page.screenshot(path=str(screenshots_dir / "omni_test4_rollback.png"))
    except Exception as e:
        await page.screenshot(path=str(screenshots_dir / "omni_test4_failed.png"))
        raise AssertionError(f"Rollback test failed: {e}") from e
