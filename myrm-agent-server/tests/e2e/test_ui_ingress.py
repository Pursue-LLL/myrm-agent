"""Public Ingress URL E2E: configure in System settings, verify SMS webhook reflects it.

Requires frontend (:3000) proxying to backend (:8080) and Patchright.

[manual]
    uv run python tests/e2e/test_ui_ingress.py
"""

from __future__ import annotations

import os
import re
import sys
import time

from patchright.sync_api import sync_playwright

FRONTEND = os.environ.get("FRONTEND_URL", "http://127.0.0.1:3000").rstrip("/")
TEST_URL = "https://ui-e2e-test-v2.ngrok.app"


def _expand_channel_list(page) -> None:
    show_more = page.get_by_role("button", name=re.compile(r"展开更多|Show more", re.I))
    if show_more.count() > 0 and show_more.first.is_visible():
        show_more.first.click()
        page.wait_for_timeout(500)


def _select_sms_channel(page) -> None:
    page.evaluate("window.localStorage.setItem('myrm-selected-channel', 'sms')")
    page.goto(f"{FRONTEND}/settings/channels", timeout=60_000)
    page.wait_for_timeout(2000)
    _expand_channel_list(page)
    sms_btn = page.get_by_role("button", name=re.compile(r"SMS \(Twilio\)", re.I))
    sms_btn.first.click()
    page.wait_for_timeout(800)


def _channel_detail_panel(page):
    return page.locator("div.hidden.lg\\:block.flex-1.min-w-0")


def _ensure_sms_channel_enabled(page) -> None:
    """SMSConfigCard renders only when channel status is not disabled."""
    detail = _channel_detail_panel(page)
    detail.wait_for(state="visible", timeout=30_000)
    toggle = detail.locator("button[role='switch']").first
    toggle.wait_for(state="visible", timeout=30_000)
    checked = toggle.get_attribute("data-state") == "checked" or toggle.get_attribute("aria-checked") == "true"
    if not checked:
        toggle.click(force=True)
        page.wait_for_timeout(2000)


def _wait_for_sms_webhook_input(page, test_url: str) -> str:
    detail = _channel_detail_panel(page)
    detail.get_by_text(re.compile(r"Webhook URL", re.I)).first.wait_for(state="visible", timeout=30_000)

    pulse = detail.locator("div.animate-pulse")
    if pulse.count() > 0:
        pulse.first.wait_for(state="hidden", timeout=30_000)

    webhook_input = detail.locator("input.font-mono, input[readonly]").first
    webhook_input.wait_for(state="visible", timeout=30_000)

    deadline = time.monotonic() + 30.0
    actual = ""
    while time.monotonic() < deadline:
        actual = webhook_input.input_value()
        if test_url in actual:
            return actual
        page.wait_for_timeout(500)
    return actual


def run_test() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 800}, locale="zh-CN")
        page = context.new_page()
        page.set_default_timeout(60_000)

        try:
            print("1. Navigate to System settings and set Public Ingress URL...")
            page.goto(f"{FRONTEND}/settings/system", timeout=60_000)
            ingress_input = page.locator("input[placeholder='https://...']")
            ingress_input.wait_for(state="visible", timeout=30_000)
            ingress_input.fill(TEST_URL, force=True)

            test_btn = page.locator("button").filter(has_text=re.compile(r"测试连通性|Test connectivity", re.I))
            if test_btn.count() > 0:
                test_btn.first.click(force=True)

            print("2. Wait for config sync debounce...")
            time.sleep(5)

            print("3. Navigate to SMS channel and verify webhook URL...")
            _select_sms_channel(page)
            _ensure_sms_channel_enabled(page)

            actual = _wait_for_sms_webhook_input(page, TEST_URL)

            print(f"   Webhook value: {actual!r}")
            assert TEST_URL in actual, f"Expected {TEST_URL!r} in webhook URL, got {actual!r}"
            assert actual.endswith("/api/v1/channels/sms/webhook"), f"Unexpected webhook path: {actual!r}"
            print("SUCCESS: SMS webhook URL reflects Public Ingress configuration.")

        except Exception as exc:
            print(f"Test failed: {exc}")
            sys.exit(1)
        finally:
            browser.close()


if __name__ == "__main__":
    run_test()
