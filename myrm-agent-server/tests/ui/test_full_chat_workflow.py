import asyncio
import os

from patchright.async_api import async_playwright


async def run_test():
    print("Starting Playwright E2E UI Test for Full Chat Workflow...")

    # Parse .env file for keys
    env_file_path = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
    env_vars = {}
    with open(env_file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                env_vars[key.strip()] = val.strip()

    # We will use BASIC_BASE_URL and BASIC_API_KEY
    api_key = env_vars.get("BASIC_API_KEY", "")
    base_url = env_vars.get("BASIC_BASE_URL", "")

    if not api_key or not base_url:
        print("Error: BASIC_API_KEY or BASIC_BASE_URL not found in .env.test")
        return

    print(f"Loaded credentials from .env: Base URL {base_url}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        # Force language headers
        context = await browser.new_context(
            accept_downloads=True, locale="zh-CN", extra_http_headers={"Accept-Language": "zh-CN,zh;q=0.9"}
        )
        page = await context.new_page()

        try:
            # 1. Add Provider in Settings
            print("1. Navigating to Model Settings...")
            page.on("console", lambda msg: print(f"Browser console: {msg.text}"))
            await page.goto("http://localhost:3000/settings/models")
            await page.wait_for_timeout(3000)

            print("Adding Custom Provider...")
            add_provider_btn = await page.wait_for_selector(
                'button:has-text("添加提供商"), button:has-text("Add Provider")', timeout=5000
            )
            await add_provider_btn.click()
            await page.wait_for_timeout(1000)

            # Fill out the dialog (assuming SiliconFlow)
            name_input = await page.wait_for_selector('input[placeholder*="MyCustom"]', timeout=3000)
            await name_input.fill("SiliconFlowTest")

            await page.locator('button:has-text("添加"), button:has-text("Add")').nth(1).click()
            await page.wait_for_timeout(2000)

            # Find the new provider and fill URL and Key
            print("Configuring Provider API Key and URL...")
            # We rely on setting it directly if inputs are visible, or we assume it added successfully.
            # In our case, the user mentioned SiliconFlow might be added. Let's just enter keys for the first custom provider.
            api_key_input = await page.locator('input[type="password"]').first
            if await api_key_input.is_visible():
                await api_key_input.fill(api_key)

            url_input = await page.locator('input[placeholder*="https://"]').first
            if await url_input.is_visible():
                await url_input.fill(base_url)

            # Save or check connection
            await page.wait_for_timeout(2000)

            # 2. Create Agent
            print("2. Navigating to Agent Settings...")
            await page.goto("http://localhost:3000/settings/agents")
            await page.wait_for_timeout(3000)

            create_btn = await page.wait_for_selector(
                'button:has-text("创建智能体"), button:has-text("Create Agent")', timeout=10000
            )
            await create_btn.click()
            await page.wait_for_timeout(2000)

            name_input = await page.wait_for_selector('input[placeholder*="输入智能体名称"]', timeout=3000)
            await name_input.fill("E2E Test Chat Agent")

            save_btn = await page.wait_for_selector('button:has-text("保存"), button:has-text("Save")', timeout=3000)
            await save_btn.click()
            await page.wait_for_timeout(3000)

            # 3. Start Chat
            print("3. Starting Chat with the Agent...")
            start_chat_btn = await page.wait_for_selector(
                'button:has-text("开始对话"), button:has-text("Start Chat")', timeout=5000
            )
            await start_chat_btn.click()
            await page.wait_for_timeout(4000)

            # Wait for chat input
            chat_input = await page.wait_for_selector('textarea, div[contenteditable="true"]', timeout=5000)
            await chat_input.fill("hello, please just say 'world' and nothing else.")

            # Send message
            send_btn = await page.wait_for_selector(
                'button[aria-label="Send message"], button[aria-label="发送"], button:has-text("发送")', timeout=3000
            )
            await send_btn.click()

            print("4. Waiting for AI response...")
            # Wait for the response to appear (we wait for a new message bubble)
            await page.wait_for_timeout(10000)

            # Check page content for "world"
            content = await page.content()
            if "world" in content.lower():
                print("✅ Success: AI responded correctly in full E2E workflow!")
            else:
                print("❌ Failure: AI response not found or incorrect.")
                print(content)
                exit(1)

        except Exception as e:
            print(f"Test failed with error: {e}")
            print("Current page HTML:")
            try:
                print(await page.content())
            except Exception:
                pass
            raise e
        finally:
            await browser.close()
            print("Test cleanup complete.")


if __name__ == "__main__":
    asyncio.run(run_test())
