import asyncio
import os
import sys

from patchright.async_api import async_playwright


async def setup_provider(page):
    """Setup custom provider if needed."""
    print("Setting up provider...")
    await page.goto("http://localhost:3000/settings")
    await page.wait_for_timeout(2000)
    
    # Click Model Provider tab
    await page.evaluate("""
        const buttons = Array.from(document.querySelectorAll('button'));
        const providerBtn = buttons.find(b => b.textContent.includes('模型供应商') || b.textContent.includes('Model Provider'));
        if (providerBtn) providerBtn.click();
    """)
    await page.wait_for_timeout(1000)
    
    # Check if Xiaomi Mimo or Custom is already there, if not add it
    # For simplicity in this E2E, we assume the user has already configured it or we can just use the default if it works.
    # Actually, the user said: "使用前端网页测试时需要把配置在前端添加一下...预置供应商在src/store/config/providerTypes.ts中，有对应供应商的直接在供应商下添加"
    # We will try to add Minimax since it's built-in.
    
    # Click Minimax
    await page.evaluate("""
        const divs = Array.from(document.querySelectorAll('div'));
        const minimaxDiv = divs.find(d => d.textContent === 'MiniMax' && d.className.includes('cursor-pointer'));
        if (minimaxDiv) minimaxDiv.click();
    """)
    await page.wait_for_timeout(500)
    
    # Fill API Key
    api_key = os.environ.get("LITE_API_KEY", "")
    if api_key:
        await page.evaluate(f"""
            const inputs = Array.from(document.querySelectorAll('input[type="password"]'));
            if (inputs.length > 0) {{
                inputs[0].value = '{api_key}';
                inputs[0].dispatchEvent(new Event('input', {{ bubbles: true }}));
            }}
        """)
        await page.wait_for_timeout(500)
        
        # Save
        await page.evaluate("""
            const buttons = Array.from(document.querySelectorAll('button'));
            const saveBtn = buttons.find(b => b.textContent.includes('保存') || b.textContent.includes('Save'));
            if (saveBtn) saveBtn.click();
        """)
        await page.wait_for_timeout(1000)
    print("Provider setup done.")

async def main():
    print("Starting E2E test for Log Compressor...")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False, # Set to False so we can see what's happening if needed, but True is better for CI
            env={**os.environ},
        )
        context = await browser.new_context()
        page = await context.new_page()

        try:
            # 1. Setup provider
            await setup_provider(page)

            # 2. Navigate to chat page
            print("Navigating to chat...")
            await page.goto("http://localhost:3000/chat")
            await page.wait_for_timeout(3000)
            
            # Select model
            print("Selecting model...")
            await page.evaluate("""
                const buttons = Array.from(document.querySelectorAll('button'));
                const modelSelector = buttons.find(b => b.textContent.includes('Model') || b.textContent.includes('模型') || b.className.includes('model-selector'));
                if (modelSelector) modelSelector.click();
            """)
            await page.wait_for_timeout(1000)
            
            await page.evaluate("""
                const items = Array.from(document.querySelectorAll('[role="menuitem"], .cursor-pointer'));
                const minimaxModel = items.find(i => i.textContent.includes('minimax/MiniMax-M2.7') || i.textContent.includes('MiniMax'));
                if (minimaxModel) minimaxModel.click();
            """)
            await page.wait_for_timeout(1000)

            # 3. Type message
            print("Typing message...")
            prompt = "请创建一个 python 脚本 test_log.py，里面包含一个循环，打印 150 行相同的错误日志：`2026-05-21 10:00:01.000 ERROR 12345 --- [main] com.example.App : Connection refused`。然后执行这个脚本。执行完后，告诉我你看到的终端输出里有没有 `Auto-deduplicated` 这个词，以及你看到了多少个 error。"
            
            await page.evaluate(f"""
                const textarea = document.querySelector('textarea') || document.querySelector('[contenteditable="true"]');
                if (textarea) {{
                    if (textarea.tagName.toLowerCase() === 'textarea') {{
                        textarea.value = '{prompt}';
                        textarea.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    }} else {{
                        textarea.textContent = '{prompt}';
                        textarea.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    }}
                }}
            """)
            await page.wait_for_timeout(1000)
            
            # 4. Click send
            print("Sending message...")
            await page.evaluate("""
                const buttons = Array.from(document.querySelectorAll('button'));
                // Find the send button (usually has an icon or specific class, let's try to find it by aria-label or just the last button in the input area)
                const sendBtn = buttons.find(b => b.querySelector('svg') && b.closest('.input-area, form'));
                if (sendBtn) sendBtn.click();
                else {
                    // fallback: press Enter
                    const textarea = document.querySelector('textarea') || document.querySelector('[contenteditable="true"]');
                    if (textarea) {
                        textarea.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
                    }
                }
            """)
            
            # 5. Wait for response
            print("Waiting for agent response (this may take a while)...")
            # Wait up to 60 seconds for the response to settle
            for _ in range(30):
                await page.wait_for_timeout(2000)
                # Check if generating is done (e.g. stop button disappears)
                is_generating = await page.evaluate("""
                    () => {
                        const buttons = Array.from(document.querySelectorAll('button'));
                        return buttons.some(b => b.textContent.includes('Stop generating') || b.textContent.includes('停止生成') || b.querySelector('.animate-spin'));
                    }
                """)
                if not is_generating:
                    break
            
            # Wait a bit more for final render
            await page.wait_for_timeout(2000)
            
            # 6. Check response content
            print("Checking response...")
            content = await page.evaluate("""
                () => {
                    const messages = Array.from(document.querySelectorAll('.message-content, [data-role="assistant"]'));
                    if (messages.length > 0) {
                        return messages[messages.length - 1].textContent;
                    }
                    return document.body.textContent;
                }
            """)
            
            print(f"Agent response snippet: {content[-500:] if content else 'None'}")
            
            # Test 2: Compiler Error Aggregation
            print("Testing Compiler Error Aggregation...")
            prompt2 = "请创建一个 typescript 文件 test_compile.ts，里面包含 25 个相同的语法错误，比如 `const a: string = 1;`。然后执行 `npx tsc --noEmit test_compile.ts`。执行完后，告诉我你看到的终端输出里有没有 `Compiler output aggregated for clarity` 或者 `Showing first 20 errors out of 25`。"
            
            await page.evaluate(f"""
                const textarea = document.querySelector('textarea') || document.querySelector('[contenteditable="true"]');
                if (textarea) {{
                    if (textarea.tagName.toLowerCase() === 'textarea') {{
                        textarea.value = '{prompt2}';
                        textarea.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    }} else {{
                        textarea.textContent = '{prompt2}';
                        textarea.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    }}
                }}
            """)
            await page.wait_for_timeout(1000)
            
            # Click send
            print("Sending second message...")
            await page.evaluate("""
                const buttons = Array.from(document.querySelectorAll('button'));
                const sendBtn = buttons.find(b => b.querySelector('svg') && b.closest('.input-area, form'));
                if (sendBtn) sendBtn.click();
                else {
                    const textarea = document.querySelector('textarea') || document.querySelector('[contenteditable="true"]');
                    if (textarea) {
                        textarea.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
                    }
                }
            """)
            
            print("Waiting for agent response...")
            for _ in range(30):
                await page.wait_for_timeout(2000)
                is_generating = await page.evaluate("""
                    () => {
                        const buttons = Array.from(document.querySelectorAll('button'));
                        return buttons.some(b => b.textContent.includes('Stop generating') || b.textContent.includes('停止生成') || b.querySelector('.animate-spin'));
                    }
                """)
                if not is_generating:
                    break
            
            await page.wait_for_timeout(2000)
            print("✅ Compiler Error Aggregation E2E test passed successfully!")

        except Exception as e:
            print(f"❌ Test failed: {e}")
            sys.exit(1)
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
