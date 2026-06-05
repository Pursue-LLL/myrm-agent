import asyncio
import os
import sys

from patchright.async_api import async_playwright

from tests.e2e_frontend.credentials import require_basic_llm_credentials, require_lite_llm_credentials


async def configure_provider(page, provider_name, api_url, api_key, model_name, is_custom=False):
    print(f"Configuring {provider_name}...")
    try:
        if is_custom:
            add_provider_btn = page.locator("button").filter(has_text="添加自定义提供商")
            if await add_provider_btn.count() == 0:
                add_provider_btn = page.locator("button").filter(has_text="添加自定义助手")
            if await add_provider_btn.count() > 0 and await add_provider_btn.first.is_visible():
                await add_provider_btn.first.click(force=True, timeout=2000)
                await page.wait_for_timeout(1000)

                inputs = await page.locator("input[type='text']").all()
                if inputs:
                    await inputs[0].fill(provider_name)

                add_btn = page.get_by_role("dialog").get_by_role("button", name="添加")
                if await add_btn.count() > 0 and await add_btn.first.is_visible():
                    await add_btn.first.click(force=True, timeout=2000)
                    await page.wait_for_timeout(1000)

        provider_item = page.locator("button").filter(has_text=provider_name)
        if await provider_item.count() > 0 and await provider_item.first.is_visible():
            await provider_item.first.click(force=True, timeout=2000)
            await page.wait_for_timeout(1000)

        url_input = page.locator("input[placeholder*='http']").first
        if await url_input.count() > 0 and await url_input.is_visible():
            await url_input.fill(api_url)
            await page.keyboard.press("Enter")
            await page.wait_for_timeout(500)

        add_key_btn = page.locator("button").filter(has_text="添加")
        if await add_key_btn.count() > 0 and await add_key_btn.first.is_visible():
            await add_key_btn.first.click(force=True, timeout=2000)
            await page.wait_for_timeout(500)
            key_input = page.locator("input[type='password']").first
            if await key_input.count() == 0:
                key_input = page.locator("input[placeholder*='sk-']").first
            if await key_input.count() > 0 and await key_input.is_visible():
                await key_input.fill(api_key)
                await page.keyboard.press("Enter")
                await page.wait_for_timeout(500)

        add_model_btn = page.locator("button").filter(has_text="添加模型")
        if await add_model_btn.count() == 0:
            add_model_btn = page.locator("button").filter(has_text="添加")
        if await add_model_btn.count() > 0 and await add_model_btn.last.is_visible():
            await add_model_btn.last.click(force=True, timeout=2000)
            await page.wait_for_timeout(500)
            model_input = page.locator("input[placeholder*='模型']").first
            if await model_input.count() > 0 and await model_input.is_visible():
                await model_input.fill(model_name)
                await page.keyboard.press("Enter")
                await page.wait_for_timeout(500)

        enable_switch = page.locator("button[role='switch']").first
        if await enable_switch.count() > 0 and await enable_switch.is_visible():
            is_checked = await enable_switch.get_attribute("aria-checked")
            if is_checked == "false":
                await enable_switch.click(force=True, timeout=2000)
                await page.wait_for_timeout(500)
    except Exception as e:
        print(f"Ignored error during configuring {provider_name}: {e}")


async def main():
    print("Starting GUI E2E test for Calendar Smart Scheduling...")

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
                await adopt.first.click(force=True, timeout=2000)
                await page.wait_for_timeout(1000)

            print("Page loaded successfully.")

            # --- Configure Providers ---
            print("Configuring providers...")
            await page.goto("http://127.0.0.1:3000/settings/models", wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)

            (basic_model.split("/")[0] if "/" in basic_model else "xiaomi_mimo")
            basic_model_name = basic_model.split("/")[1] if "/" in basic_model else basic_model
            await configure_provider(page, "Xiaomi MiMo", basic_base_url, basic_api_key, basic_model_name)

            lite_model.split("/")[0] if "/" in lite_model else "minimax"
            lite_model_name = lite_model.split("/")[1] if "/" in lite_model else lite_model
            await configure_provider(page, "MiniMax", lite_base_url, lite_api_key, lite_model_name)

            # --- Test Calendar Agent Scheduling ---
            print("Testing Calendar Tool from Frontend UI...")
            await page.goto("http://127.0.0.1:3000", wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)

            # Click the Agent button
            if await page.get_by_role("radio", name="智能代理").count() > 0:
                await page.get_by_role("radio", name="智能代理").click(force=True, timeout=2000)
                await page.wait_for_timeout(500)

            chat_input = None
            for _ in range(5):
                textareas = await page.locator("textarea").all()
                for ta in textareas:
                    if await ta.is_visible() and not await ta.get_attribute("readonly"):
                        chat_input = ta
                        break
                if chat_input:
                    break
                await asyncio.sleep(1)

            if chat_input:
                prompt_text = "请调用 find_optimal_meeting_slots 工具，帮我排期一下明天下午有没有时间可以开会。如果工具返回了包含 <timeslotpicker> 相关的HTML代码，请你务必原封不动地将其直接打印在你的最终回答里，这样前端才能渲染卡片！"
                await chat_input.fill(prompt_text)
                await page.keyboard.press("Enter")

                print("Waiting for Agent to run and invoke tool...")
                try:
                    await page.wait_for_function(
                        '() => document.querySelectorAll(".prose").length > 0',
                        timeout=90000,
                    )
                    await page.wait_for_timeout(5000)  # Give it 5s to render anything
                    print("✅ GUI E2E SUCCESS: End-to-End messaging loop completed.")
                    sys.exit(0)
                except Exception as e:
                    body = await page.content()
                    with open("debug_calendar_e2e_timeout.html", "w") as f:
                        f.write(body)
                    print(f"❌ GUI E2E FAIL: Timed out waiting for response. {e}")
                    sys.exit(1)
            else:
                body = await page.content()
                with open("debug_calendar_e2e.html", "w") as f:
                    f.write(body)
                print("Error: Chat input not found.")
                sys.exit(1)

        except Exception as e:
            print(f"Error during E2E testing: {e}")
            sys.exit(1)
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
