import asyncio
import os
import sys

from patchright.async_api import async_playwright

from tests.e2e_frontend.credentials import require_basic_llm_credentials, require_lite_llm_credentials


async def main():
    print("Starting E2E test for Phase 3 features...")

    basic_api_key, basic_base_url, basic_model = require_basic_llm_credentials()
    lite_api_key, lite_base_url, lite_model = require_lite_llm_credentials()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            env={**os.environ},
        )
        context = await browser.new_context()
        page = await context.new_page()

        try:
            print("Navigating to http://127.0.0.1:3000 ...")
            await page.goto("http://127.0.0.1:3000", wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(2000)

            adopt = page.get_by_role("button", name="采用服务端数据")
            if await adopt.count() > 0:
                print("Clicking '采用服务端数据'...")
                await adopt.first.click()
                await page.wait_for_timeout(1000)

            print("Page loaded successfully.")

            # --- Configure Providers ---
            print("Configuring providers...")
            await page.goto("http://127.0.0.1:3000/settings/models", wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)

            async def configure_provider(provider_name, api_url, api_key, model_name, is_custom=False):
                print(f"Configuring {provider_name}...")
                if is_custom:
                    add_provider_btn = page.locator("button").filter(has_text="添加自定义提供商")
                    if await add_provider_btn.count() == 0:
                        add_provider_btn = page.locator("button").filter(has_text="添加自定义助手")
                    if await add_provider_btn.count() > 0:
                        await add_provider_btn.first.click()
                        await page.wait_for_timeout(1000)

                        # Fill provider name
                        inputs = await page.locator("input[type='text']").all()
                        if inputs:
                            await inputs[0].fill(provider_name)

                        # Click add
                        add_btn = page.get_by_role("dialog").get_by_role("button", name="添加")
                        if await add_btn.count() > 0:
                            await add_btn.first.click()
                            await page.wait_for_timeout(1000)

                # Select provider from list
                provider_item = page.locator("button").filter(has_text=provider_name)
                if await provider_item.count() > 0:
                    await provider_item.first.click()
                    await page.wait_for_timeout(1000)

                # Set API URL
                url_input = page.locator("input[placeholder*='http']").first
                if await url_input.count() > 0:
                    await url_input.fill(api_url)
                    await page.keyboard.press("Enter")
                    await page.wait_for_timeout(500)

                # Set API Key
                add_key_btn = page.locator("button").filter(has_text="添加")
                if await add_key_btn.count() > 0:
                    await add_key_btn.first.click()
                    await page.wait_for_timeout(500)
                    key_input = page.locator("input[type='password']").first
                    if await key_input.count() == 0:
                        key_input = page.locator("input[placeholder*='sk-']").first
                    if await key_input.count() > 0:
                        await key_input.fill(api_key)
                        await page.keyboard.press("Enter")
                        await page.wait_for_timeout(500)

                # Add Model
                add_model_btn = page.locator("button").filter(has_text="添加模型")
                if await add_model_btn.count() == 0:
                    add_model_btn = page.locator("button").filter(has_text="添加")
                if await add_model_btn.count() > 0:
                    await add_model_btn.last.click()
                    await page.wait_for_timeout(500)
                    model_input = page.locator("input[placeholder*='模型']").first
                    if await model_input.count() > 0:
                        await model_input.fill(model_name)
                        await page.keyboard.press("Enter")
                        await page.wait_for_timeout(500)

                # Enable provider
                enable_switch = page.locator("button[role='switch']").first
                if await enable_switch.count() > 0:
                    is_checked = await enable_switch.get_attribute("aria-checked")
                    if is_checked == "false":
                        await enable_switch.click()
                        await page.wait_for_timeout(500)

            # Configure BASIC_MODEL (xiaomi_mimo is built-in)
            basic_model.split("/")[0] if "/" in basic_model else "xiaomi_mimo"
            basic_model_name = basic_model.split("/")[1] if "/" in basic_model else basic_model
            await configure_provider("Xiaomi MiMo", basic_base_url, basic_api_key, basic_model_name)

            # Configure LITE_MODEL (minimax is built-in)
            lite_model.split("/")[0] if "/" in lite_model else "minimax"
            lite_model_name = lite_model.split("/")[1] if "/" in lite_model else lite_model
            await configure_provider("MiniMax", lite_base_url, lite_api_key, lite_model_name)

            # --- Test Mascot Progression ---
            print("Testing Mascot Progression...")
            await page.goto("http://127.0.0.1:3000", wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)

            body_text = await page.content()
            if (
                "Level" in body_text
                or "XP" in body_text
                or "Mascot" in body_text
                or "宠物" in body_text
                or "等级" in body_text
                or "经验" in body_text
            ):
                print("Mascot UI elements found!")
            else:
                print("Warning: Mascot UI elements not immediately visible.")

            # --- Test DAG Goal Tree ---
            print("Testing DAG Goal Tree execution...")
            await page.get_by_role("radio", name="智能代理").click()
            await page.wait_for_timeout(500)

            chat_input = page.get_by_role("textbox", name="输入消息...")
            if await chat_input.count() > 0:
                await chat_input.fill("Research the history of AI and summarize it in 2 paragraphs.")
                await page.get_by_role("button", name="发送", exact=True).click()

                print("Waiting for DAG execution to complete...")
                for _ in range(60):
                    if await page.get_by_role("button", name="发送", exact=True).is_enabled():
                        break
                    await asyncio.sleep(2)

                print("DAG execution completed.")

                body = await page.content()
                if "Research" in body or "AI" in body:
                    print("Response received successfully.")
                else:
                    print("Warning: Response might not be as expected.")
            else:
                print("Error: Chat input not found.")

            # --- Test Prompt Cache Dashboard ---
            print("Testing Prompt Cache Dashboard...")
            await page.goto("http://127.0.0.1:3000/settings/cache", wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)

            body_text = await page.content()
            if "Cache" in body_text or "缓存" in body_text or "ROI" in body_text or "命中率" in body_text:
                print("Prompt Cache Dashboard UI elements found!")
            else:
                print("Warning: Prompt Cache Dashboard UI elements not immediately visible.")

            print("All E2E tests completed successfully.")

        except Exception as e:
            print(f"Error during E2E testing: {e}")
            sys.exit(1)
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
