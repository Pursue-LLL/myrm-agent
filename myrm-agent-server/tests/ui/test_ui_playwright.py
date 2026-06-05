import sys
import time

from patchright.sync_api import sync_playwright


def run_test():
    with sync_playwright() as p:
        # Launch browser
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        page = context.new_page()

        try:
            print("1. Navigating to http://localhost:3000/settings/system ...")
            page.goto("http://localhost:3000/settings/system", timeout=60000)

            print("2. Wait for loading to finish...")
            try:
                page.wait_for_selector("input[placeholder='https://...']", timeout=30000)
            except Exception as e:
                print("Could not find input. Printing page content:")
                print(page.content())
                raise e

            # Listen to all API responses
            page.on(
                "response",
                lambda response: (
                    print(f"<< {response.status} {response.url}") if "api/v1/system/ingress-url" in response.url else None
                ),
            )

            print("3. Locating Public Ingress Input...")
            ingress_input = page.locator("input[placeholder='https://...']")

            # Clear and type new URL
            test_url = "https://ui-e2e-test-v2.ngrok.app"
            ingress_input.fill(test_url, force=True)

            # Click "测试连通性" just to trigger a blur/save (though typing already triggers Zustand set)
            print("4. Testing connection button...")
            test_btn = page.locator("button:has-text('测试连通性')")
            try:
                test_btn.click(timeout=5000, force=True)
            except Exception as e:
                print("Could not click test button. Printing page content snippet:")
                content = page.content()

                # Find dialogs or modals text
                print(content[:1500])
                raise e

            print("Wait 5 seconds for backend to sync config...")
            time.sleep(5)  # Give it time to save via API

            print("5. Navigating to Channels (SMS) to verify webhook URL...")
            # Set localStorage before navigation so it defaults to SMS channel
            page.evaluate("window.localStorage.setItem('myrm-selected-channel', 'sms')")

            page.goto("http://localhost:3000/settings/channels", timeout=15000)

            print("6. Wait for loading to finish and SMS config card to fetch ingress URL...")
            page.wait_for_timeout(3000)

            print("7. Looking for SMS Webhook URL in input values...")
            inputs = page.locator("input").all()
            found = False
            for i, inp in enumerate(inputs):
                try:
                    val = inp.input_value()
                    print(f"Input {i} value: '{val}'")
                    if test_url in val:
                        found = True
                        print(f"SUCCESS: Found test URL '{test_url}' in input value: {val}")
                        break
                except Exception as e:
                    print(f"Input {i} error: {e}")
                    pass

            if not found:
                print("FAIL: Could not find test URL in any input!")
                raise AssertionError(f"Test URL '{test_url}' not found in any input value!")

            print("SUCCESS: UI correctly updates dependent URLs based on Public Ingress Input!")

        except Exception as e:
            print(f"Test failed: {e}")
            sys.exit(1)
        finally:
            browser.close()


if __name__ == "__main__":
    run_test()
