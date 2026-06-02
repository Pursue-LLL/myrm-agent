import asyncio

from patchright.async_api import async_playwright

from tests.e2e_frontend.credentials import require_lite_llm_credentials


async def run_test():
    lite_api_key, _, _ = require_lite_llm_credentials()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        print("Navigating to settings...")
        await page.goto("http://localhost:3000/settings/models")
        await page.wait_for_timeout(2000)

        # Click "保留本地修改" if conflict dialog appears
        try:
            conflict_btn = await page.wait_for_selector('button:has-text("保留本地修改")', timeout=3000)
            if conflict_btn:
                await conflict_btn.click()
                print("Clicked '保留本地修改'")
        except Exception:
            pass

        # Add Minimax provider
        print("Adding Minimax provider...")
        # Find the button that contains "Minimax"
        minimax_btn = await page.wait_for_selector('button:has-text("Minimax")', timeout=5000)
        if minimax_btn:
            await minimax_btn.click()
            await page.wait_for_timeout(1000)

            # Enter API Key
            api_key_input = await page.wait_for_selector('input[placeholder="sk-..."]', timeout=3000)
            if api_key_input:
                await api_key_input.fill(lite_api_key)

                # Click Add
                add_btn = await page.wait_for_selector('button:has-text("添加"):not([disabled])', timeout=3000)
                if add_btn:
                    await add_btn.click()
                    print("Minimax API Key added.")

        # Add Minimax model
        print("Adding Minimax model...")
        add_model_btn = await page.wait_for_selector('button:has-text("添加模型")', timeout=3000)
        if add_model_btn:
            await add_model_btn.click()
            model_input = await page.wait_for_selector('input[placeholder="输入模型名称，如 gpt-4o"]', timeout=3000)
            if model_input:
                await model_input.fill("MiniMax-M2.7")
                add_btn = await page.wait_for_selector('button:has-text("添加"):not([disabled])', timeout=3000)
                if add_btn:
                    await add_btn.click()
                    print("Minimax model added.")

        # Enable ask_question_tool in Agent Settings
        print("Navigating to Agent Settings...")
        await page.goto("http://localhost:3000/settings/agent")
        await page.wait_for_timeout(2000)

        # Find ask_question_tool checkbox and enable it
        try:
            ask_question_checkbox = await page.wait_for_selector('input[type="checkbox"][id="ask_question_tool"]', timeout=3000)
            if ask_question_checkbox:
                is_checked = await ask_question_checkbox.is_checked()
                if not is_checked:
                    await ask_question_checkbox.click()
                    print("Enabled ask_question_tool.")
        except Exception as e:
            print(f"Could not find or click ask_question_tool checkbox: {e}")

        # Start a new chat
        print("Navigating to Chat...")
        await page.goto("http://localhost:3000/")
        await page.wait_for_timeout(2000)

        # Type a message that triggers clarification
        print("Sending message to trigger clarification...")
        chat_input = await page.wait_for_selector('textarea[placeholder*="输入"]', timeout=3000)
        if chat_input:
            await chat_input.fill("Please ask me a clarification question using the ask_question_tool.")
            await page.keyboard.press("Enter")

            print("Waiting for clarification form...")
            # Wait for the clarification form to appear
            form_element = await page.wait_for_selector(".clarification-form, form", timeout=30000)
            if form_element:
                print("Clarification form appeared!")

                # Try to fill out the form
                inputs = await form_element.query_selector_all('input[type="text"], input[type="radio"], input[type="checkbox"]')
                if inputs:
                    for input_el in inputs:
                        input_type = await input_el.get_attribute("type")
                        if input_type == "text":
                            await input_el.fill("This is my answer.")
                        elif input_type in ["radio", "checkbox"]:
                            await input_el.click()
                            break  # Just click the first one

                # Submit the form
                submit_btn = await form_element.query_selector('button[type="submit"], button:has-text("提交")')
                if submit_btn:
                    await submit_btn.click()
                    print("Submitted clarification answer.")

                    # Wait for agent to resume
                    print("Waiting for agent to resume...")
                    await page.wait_for_timeout(10000)
                    print("Test completed successfully.")
                else:
                    print("Could not find submit button.")
            else:
                print("Clarification form did not appear.")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(run_test())
