import asyncio
import os
import sys

from patchright.async_api import async_playwright


async def main():
    print("Starting E2E test for Agent Time Machine GUI features...")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            env={**os.environ},
        )
        context = await browser.new_context()
        page = await context.new_page()

        try:
            print("Navigating to http://localhost:3000 ...")
            await page.goto("http://localhost:3000", wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(2000)

            adopt = page.get_by_role("button", name="采用服务端数据")
            if await adopt.count() > 0:
                print("Clicking '采用服务端数据'...")
                await adopt.first.click()
                await page.wait_for_timeout(1000)

            print("Page loaded successfully. Navigating to Agents settings...")

            await page.goto("http://localhost:3000/settings/agents", wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)

            # Step 1: Create a new Agent
            print("Creating a new Agent...")
            await page.get_by_role("button", name="创建智能体").click()
            await page.wait_for_timeout(2000)

            await page.get_by_placeholder("输入智能体名称").fill("Time Machine Test Agent")
            await page.get_by_placeholder("描述智能体的用途").fill("This is the original description v1.")

            print("Saving v1...")
            await page.get_by_role("button", name="保存").click()

            # Wait for URL to contain agentId
            print("Waiting for redirect to edit page...")
            await page.wait_for_url("**/settings/agents?agentId=**", timeout=10000)

            # Wait for the save button to become disabled (meaning data is loaded and no changes)
            save_button = page.get_by_role("button", name="保存")
            await save_button.wait_for(state="visible")

            # Polling until disabled
            for _ in range(10):
                if await save_button.is_disabled():
                    break
                await page.wait_for_timeout(500)

            # Step 2: Edit to create v2 snapshot
            print("Modifying description to v2...")
            await page.get_by_placeholder("描述智能体的用途").fill("This is the updated description v2.")

            # Wait for save button to be enabled
            for _ in range(10):
                if await save_button.is_enabled():
                    break
                await page.wait_for_timeout(500)

            print("Saving v2...")
            async with page.expect_response(
                lambda response: "/api/v1/user-agents/" in response.url and response.request.method == "PUT"
            ) as response_info:
                await save_button.click()

            await response_info.value
            await page.wait_for_timeout(1000)  # Wait for React state to settle

            # Step 3: Undo functionality
            print("Clicking Undo (撤销上一次配置更改)...")
            undo_buttons = await page.get_by_role("button", name="撤销上一次配置更改").all()
            if not undo_buttons:
                # If using the icon title, maybe the text is different. Let's try locating by text
                undo_buttons = await page.get_by_text("撤销上一次配置更改").all()

            if undo_buttons:
                await undo_buttons[0].click()
                await page.wait_for_timeout(1000)
                print("Confirming Undo...")
                # The confirmation button is "确认撤销" or "确认撤销上一次配置更改"
                # Check which one exists
                confirm_btn = page.get_by_role("button", name="确认撤销")
                if await confirm_btn.count() > 0:
                    async with page.expect_response(
                        lambda response: "/rollback" in response.url and response.request.method == "POST"
                    ) as response_info:
                        await confirm_btn.first.click()
                else:
                    confirm_btn = page.get_by_role("button", name="确认撤销上一次配置更改")
                    if await confirm_btn.count() > 0:
                        async with page.expect_response(
                            lambda response: "/rollback" in response.url and response.request.method == "POST"
                        ) as response_info:
                            await confirm_btn.first.click()
                    else:
                        print("Error: Could not find Confirm Undo button.")
                        sys.exit(1)

                await response_info.value
                resp_json = await response_info.value
                print("Rollback API response:", await resp_json.json())
                print("Rollback API responded, waiting for reload...")
                await page.wait_for_timeout(2000)  # Wait for reloadAgent() to populate UI

                # Fetch directly from API to verify DB state
                import httpx

                agent_url = page.url
                import urllib.parse

                agent_id = urllib.parse.parse_qs(urllib.parse.urlparse(agent_url).query)["agentId"][0]
                api_res = httpx.get(f"http://localhost:8080/api/v1/user-agents/{agent_id}").json()
                print("DB Description after undo:", api_res["data"]["description"])

                # Verify prompt is back to v1
                content = await page.get_by_placeholder("描述智能体的用途").input_value()
                print(f"Description after undo: {content}")
                if "v1" not in content:
                    print("Error: Description didn't revert to v1 after undo!")
                    sys.exit(1)
            else:
                print("Error: Could not find Undo button.")
                sys.exit(1)

            # Step 4: Modify again to create v3
            print("Modifying description to v3...")
            await page.get_by_placeholder("描述智能体的用途").fill("This is the newest description v3.")

            # Wait for save button to be enabled
            for _ in range(10):
                if await save_button.is_enabled():
                    break
                await page.wait_for_timeout(500)

            print("Saving v3...")
            async with page.expect_response(
                lambda response: "/api/v1/user-agents/" in response.url and response.request.method == "PUT"
            ) as response_info:
                await save_button.click()

            await response_info.value
            await page.wait_for_timeout(1000)  # Wait for React state to settle

            # Step 5: Time Machine
            print("Opening Time Machine...")
            view_all = page.get_by_text("在时光机中查看所有快照")
            if await view_all.count() > 0:
                await view_all.click()
            else:
                # Click the accordion directly if link not found
                await page.get_by_text("配置时光机").click()
            await page.wait_for_timeout(2000)

            print("Restoring to v1 via Time Machine...")
            restore_btns = await page.get_by_role("button", name="恢复此版本").all()
            if len(restore_btns) >= 2:
                # Click the LAST one (oldest)
                await restore_btns[-1].click()
                await page.wait_for_timeout(1000)
                print("Confirming Restore...")
                async with page.expect_response(
                    lambda response: "/rollback" in response.url and response.request.method == "POST"
                ) as response_info:
                    # AlertDialogAction is sometimes tricky, use locator
                    await page.locator('button:has-text("确认恢复")').click()
                await response_info.value
                await page.wait_for_timeout(3000)

                # Verify prompt is back to v1
                content = await page.get_by_placeholder("描述智能体的用途").input_value()
                print(f"Description after Time Machine restore: {content}")
                if "v1" not in content:
                    print("Error: Description didn't revert to v1 after Time Machine restore!")
                    sys.exit(1)
            else:
                print("Error: Could not find enough '恢复此版本' buttons.")
                sys.exit(1)

            print("All Time Machine E2E tests passed successfully!")

        except Exception as e:
            print(f"E2E Test failed with error: {e}")
            await page.screenshot(path="timeout_chat.png", full_page=True)
            sys.exit(1)
        finally:
            await context.close()
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
