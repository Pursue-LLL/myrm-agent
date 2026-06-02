import asyncio
import json
import os

from patchright.async_api import async_playwright


async def run_test():
    print("Starting Playwright E2E UI Test for Agent Import/Export...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        # Force language headers
        context = await browser.new_context(
            accept_downloads=True, locale="zh-CN", extra_http_headers={"Accept-Language": "zh-CN,zh;q=0.9"}
        )
        page = await context.new_page()

        try:
            print("1. Navigating to Agent Settings...")
            page.on("console", lambda msg: print(f"Browser console: {msg.text}"))
            await page.goto("http://localhost:3000/settings/agents")
            await page.wait_for_timeout(3000)

            # Dismiss any dialogs like "保留本地修改"
            try:
                conflict_btn = await page.wait_for_selector(
                    'button:has-text("保留本地修改"), button:has-text("Keep Local")', timeout=2000
                )
                if conflict_btn:
                    await conflict_btn.click()
            except Exception:
                pass

            await page.wait_for_timeout(2000)

            print("2. Creating a test agent for export...")
            create_btn = await page.wait_for_selector(
                'button:has-text("创建智能体"), button:has-text("Create Agent")', timeout=10000
            )
            await create_btn.click()
            await page.wait_for_timeout(2000)

            # Fill the name
            name_input = await page.wait_for_selector("input", timeout=3000)
            await name_input.fill("UI Test Export Agent")

            # Click save
            save_btn = await page.wait_for_selector('button:has-text("保存"), button:has-text("Save")', timeout=3000)
            await save_btn.click()
            await page.wait_for_timeout(3000)

            print("3. Exporting the agent...")
            export_btn = await page.wait_for_selector(
                'button:has-text("导出配置"), button:has-text("Export"), button[title="导出智能体配置"]', timeout=5000
            )

            # Start waiting for download
            async with page.expect_download() as download_info:
                await export_btn.click()
            download = await download_info.value

            download_path = "test_export_agent.json"
            await download.save_as(download_path)
            print(f"Downloaded agent config to {download_path}")

            with open(download_path, "r", encoding="utf-8") as f:
                agent_data = json.load(f)

            agent_data["name"] = "UI Test Imported Agent"

            import_path = "test_import_agent.json"
            with open(import_path, "w", encoding="utf-8") as f:
                json.dump(agent_data, f, ensure_ascii=False)

            print("4. Go back to agent list to import...")
            await page.goto("http://localhost:3000/settings/agents")
            await page.wait_for_timeout(3000)

            print("5. Importing the modified agent...")
            file_input = await page.locator('input[type="file"][accept=".json,.agent.json"]').first
            await file_input.set_input_files(import_path)

            print("Waiting for import to complete...")
            await page.wait_for_timeout(4000)

            imported_agent = await page.wait_for_selector('text="UI Test Imported Agent"', timeout=5000)
            if imported_agent:
                print("✅ Success: Imported agent found in the list!")
            else:
                print("❌ Failure: Imported agent not found.")
                exit(1)

        except Exception as e:
            print(f"Test failed with error: {e}")
            print("Current page HTML:")
            print(await page.content())
            raise e
        finally:
            if os.path.exists("test_export_agent.json"):
                os.remove("test_export_agent.json")
            if os.path.exists("test_import_agent.json"):
                os.remove("test_import_agent.json")
            await browser.close()
            print("Test cleanup complete.")


if __name__ == "__main__":
    asyncio.run(run_test())
