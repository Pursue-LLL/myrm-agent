import asyncio

from patchright.async_api import async_playwright


async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(viewport={"width": 1280, "height": 800})
        page = await context.new_page()

        await page.goto("http://127.0.0.1:3000")
        await page.wait_for_timeout(1500)
        await page.evaluate("window.sessionStorage.setItem('myrm_boot_shown', '1')")
        await page.reload()
        await page.wait_for_timeout(2000)

        await page.keyboard.press("Escape")
        await asyncio.sleep(0.5)

        html = await page.content()
        with open("debug_ui.html", "w") as f:
            f.write(html)

        await browser.close()


if __name__ == "__main__":
    asyncio.run(run())
