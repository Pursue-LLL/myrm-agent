import subprocess
import time
from pathlib import Path

from patchright.sync_api import sync_playwright


def test_goal_branch_ui():
    workspace_dir = str(Path(__file__).resolve().parents[3])

    # Ensure we are on main branch initially
    subprocess.run(["git", "checkout", "main"], cwd=workspace_dir, capture_output=True)

    with sync_playwright() as p:
        # Launch browser
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        page = context.new_page()

        print("Navigating to http://localhost:3000/chat...")
        page.goto("http://localhost:3000/chat", wait_until="domcontentloaded")

        # Wait for the chat input to be visible
        try:
            page.wait_for_selector("textarea", timeout=15000)
            print("Chat interface loaded. URL:", page.url)
        except Exception as e:
            print("Failed to load chat interface:", e)
            print("URL:", page.url)
            browser.close()
            return

        print("Body text:", page.locator("body").inner_text())

        # Send a message to start a goal
        print("Sending message to initiate a goal...")
        page.fill("textarea", "/goal Write a 5-step plan to build a snake game.")
        page.keyboard.press("Enter")

        # Wait for the Goal Status Card to appear (we look for some Goal text or element)
        print("Waiting for Goal to become active...")
        # Since we don't know the exact class, we wait for a generic indicator that AI is processing or Goal is active.
        # We can also wait for the EventBus to be connected. Let's just wait a few seconds.
        time.sleep(10)
        print("Body text after 10s:", page.locator("body").inner_text())

        # Now, trigger a branch switch
        test_branch = "e2e-test-branch-ui"
        print(f"Switching git branch to {test_branch}...")
        subprocess.run(
            ["git", "checkout", "-b", test_branch],
            cwd=workspace_dir,
            capture_output=True,
        )

        # Give the backend 2 seconds to detect and push SSE
        time.sleep(2)

        # Check if toast appeared or badge appeared in the page
        content = page.content()

        if test_branch in content:
            print(f"SUCCESS: Branch '{test_branch}' found in the UI!")
        else:
            print(f"FAILED: Branch '{test_branch}' NOT found in the UI.")
            page.screenshot(path="screenshot_failed_branch1.png")
            # Let's wait a bit longer and check again
            time.sleep(10)
            content = page.content()
            if test_branch in content:
                print(f"SUCCESS (after delay): Branch '{test_branch}' found in the UI!")
            else:
                print("STILL FAILED.")
                page.screenshot(path="screenshot_failed_branch2.png")

        # Clean up: switch back to main and delete test branch
        print("Switching back to main and cleaning up...")
        subprocess.run(["git", "checkout", "main"], cwd=workspace_dir, capture_output=True)
        subprocess.run(["git", "branch", "-D", test_branch], cwd=workspace_dir, capture_output=True)

        browser.close()


if __name__ == "__main__":
    test_goal_branch_ui()
