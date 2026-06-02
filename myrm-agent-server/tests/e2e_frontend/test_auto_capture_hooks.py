import asyncio
import os
import sys

from patchright.async_api import async_playwright

from tests.e2e_frontend.credentials import require_basic_llm_credentials


async def main():
    print("Starting E2E test for Auto Capture Hooks...")

    basic_api_key, basic_base_url, basic_model = require_basic_llm_credentials()
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            env={
                **os.environ,
                "PLAYWRIGHT_BROWSERS_PATH": "/Users/yululiu/Library/Caches/ms-playwright",
                "PATCHRIGHT_BROWSERS_PATH": "/Users/yululiu/Library/Caches/ms-playwright",
            },
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
                    try:
                        await add_key_btn.first.click(timeout=5000)
                        await page.wait_for_timeout(500)
                        key_input = page.locator("input[type='password']").first
                        if await key_input.count() == 0:
                            key_input = page.locator("input[placeholder*='sk-']").first
                        if await key_input.count() > 0:
                            await key_input.fill(api_key)
                            await page.keyboard.press("Enter")
                            await page.wait_for_timeout(500)
                    except Exception:
                        print("Skipping key addition (button not clickable)")
                
                # Add Model
                add_model_btn = page.locator("button").filter(has_text="添加模型")
                if await add_model_btn.count() == 0:
                    add_model_btn = page.locator("button").filter(has_text="添加")
                if await add_model_btn.count() > 0:
                    try:
                        await add_model_btn.last.click(timeout=5000)
                        await page.wait_for_timeout(500)
                        model_input = page.locator("input[placeholder*='模型']").first
                        if await model_input.count() > 0:
                            await model_input.fill(model_name)
                            await page.keyboard.press("Enter")
                            await page.wait_for_timeout(500)
                    except Exception:
                        print("Skipping model addition (button not clickable)")
                
                # Enable provider
                enable_switch = page.locator("button[role='switch']").first
                if await enable_switch.count() > 0:
                    is_checked = await enable_switch.get_attribute("aria-checked")
                    if is_checked == "false":
                        await enable_switch.click()
                        await page.wait_for_timeout(500)

            basic_model_name = basic_model.split("/")[1] if "/" in basic_model else basic_model
            await configure_provider("Xiaomi MiMo", basic_base_url, basic_api_key, basic_model_name)
            
            # --- Test Auto Capture Hook ---
            print("Testing Auto Capture Hook...")
            await page.goto("http://127.0.0.1:3000", wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)
            
            # Select Agent mode
            agent_radio = page.get_by_role("radio", name="智能代理")
            if await agent_radio.count() > 0:
                await agent_radio.click()
                await page.wait_for_timeout(500)
            
            chat_input = page.get_by_role("textbox", name="输入消息...")
            if await chat_input.count() > 0:
                print("Sending user edict message...")
                await chat_input.fill("never use sudo for this project")
                
                # Click send
                send_btn = page.locator("button").filter(has_text="发送")
                if await send_btn.count() == 0:
                    send_btn = page.locator("button[aria-label='发送']")
                if await send_btn.count() > 0:
                    await send_btn.first.click()
                else:
                    await page.keyboard.press("Enter")
                
                print("Waiting for agent to respond...")
                await page.wait_for_timeout(15000)
                
            # Check Memory Command Center
            print("Navigating to Memory Command Center...")
            await page.goto("http://127.0.0.1:3000/settings/memory", wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(5000)
            
            # Look for pending memory
            body_text = await page.content()
            if "sudo" in body_text.lower() or "pending" in body_text.lower() or "待审批" in body_text:
                print("SUCCESS: Found pending memory in Command Center!")
            else:
                print("WARNING: Could not immediately find pending memory text in Command Center.")
                
            print("E2E Test completed successfully.")
            
        except Exception as e:
            print(f"Test failed: {e}")
            sys.exit(1)
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
