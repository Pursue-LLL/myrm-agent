#!/usr/bin/env python3
"""WFEL settings UI smoke check via CDP (real Chrome :9222, app :3000)."""

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

        found = page.evaluate(
            """() => {
              const needle = '网页抓取远程兜底';
              const el = [...document.querySelectorAll('h3,button,section')].find(
                (n) => (n.textContent || '').includes(needle)
              );
              if (!el) return { ok: false, reason: 'title-not-in-dom' };
              el.scrollIntoView({ block: 'center' });
              return { ok: true, tag: el.tagName, text: (el.textContent || '').slice(0, 80) };
            }"""
        )
        if not found.get("ok"):
            print(json.dumps({"ok": False, "error": found.get("reason", "missing")}))
            return 1

        section_btn = page.locator("section").filter(has_text="网页抓取远程兜底").locator("button").first
        section_btn.click(timeout=TIMEOUT_MS)
        page.wait_for_timeout(500)

        verify_visible = page.get_by_role("button", name="测试 Jina").is_visible()
        print(
            json.dumps(
                {
                    "ok": verify_visible,
                    "url": page.url,
                    "checks": ["title-in-dom", "expand", "verifyJina"],
                    "title": found.get("text"),
                }
            )
        )
        return 0 if verify_visible else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        raise SystemExit(1) from exc
