import asyncio

from patchright.async_api import async_playwright


async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        print("Navigating to http://localhost:3000/")
        await page.goto("http://localhost:3000/")

        print("Typing message...")
        await page.fill(
            'textarea[placeholder="输入消息..."]', "帮我写一个 React 计数器组件，使用 tailwindcss 居中显示，包含加减按钮。"
        )

        print("Clicking send...")
        await page.keyboard.press("Enter")

        print("Waiting for artifact to be generated...")
        try:
            # Wait for the Sandpack editor or CodePreview to appear
            await page.wait_for_selector(".sp-editor", timeout=30000)
            print("Artifact generated successfully!")

            print("E2E Test Passed!")
        except Exception as e:
            print(f"E2E Test Failed: {e}")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(run())
