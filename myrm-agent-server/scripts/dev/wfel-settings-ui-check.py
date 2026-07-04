#!/usr/bin/env python3
"""WFEL settings UI full-path check: expand card, click Test Jina, assert API response."""

from __future__ import annotations

import json
import sys

from patchright.sync_api import sync_playwright

CDP = "http://127.0.0.1:9222"
URL = "http://127.0.0.1:3000/settings/search"
TIMEOUT_MS = 8000


def main() -> int:
    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(CDP, timeout=TIMEOUT_MS)
        context = browser.contexts[0] if browser.contexts else browser.new_context()
        page = next((pg for pg in context.pages if "settings/search" in pg.url), None)
        if page is None:
            page = context.new_page()
            page.goto(URL, wait_until="domcontentloaded", timeout=TIMEOUT_MS)
        else:
            page.reload(wait_until="domcontentloaded", timeout=TIMEOUT_MS)

        page.set_default_timeout(TIMEOUT_MS)
        page.wait_for_timeout(2000)

        section = page.locator("section").filter(has_text="网页抓取远程兜底")
        section.locator("button").first.click(timeout=TIMEOUT_MS)
        page.wait_for_timeout(400)

        verify_btn = page.get_by_role("button", name="测试 Jina")
        verify_btn.wait_for(state="visible", timeout=TIMEOUT_MS)

        with page.expect_response(
            lambda r: "/integrations/web-fetch/verify" in r.url and r.request.method == "POST",
            timeout=TIMEOUT_MS,
        ) as resp_info:
            verify_btn.click()

        response = resp_info.value
        status = response.status
        body_text = response.text()
        try:
            body = json.loads(body_text)
        except json.JSONDecodeError:
            body = {"raw": body_text[:200]}

        ok = status in (200, 502)
        print(
            json.dumps(
                {
                    "ok": ok,
                    "url": page.url,
                    "verify_status": status,
                    "verify_success": body.get("success") if isinstance(body, dict) else None,
                    "checks": ["expand", "click_verify_jina", "api_response"],
                },
                ensure_ascii=False,
            )
        )
        return 0 if ok else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        raise SystemExit(1) from exc
