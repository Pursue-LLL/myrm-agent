"""Real frontend flow: Preferences language section + channel sync + locale persistence.

Read-only on `.env`. Requires frontend (:3000) and backend (:8080).

[manual]
    uv run python tests/e2e/real_channel_locale_preferences_flow.py

[pytest — skipped unless MYRM_E2E_REAL_FRONTEND_STACK=1]
    MYRM_E2E_REAL_FRONTEND_STACK=1 uv run pytest tests/e2e/real_channel_locale_preferences_flow.py -v -n0
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import urllib.error
import urllib.request

import pytest
from patchright.async_api import Page, async_playwright

FRONTEND_BASE = os.environ.get("MYRM_E2E_FRONTEND_URL", "http://localhost:3000").rstrip("/")
BACKEND_BASE = os.environ.get("MYRM_E2E_BACKEND_URL", "http://localhost:8080").rstrip("/")

pytestmark = pytest.mark.skipif(
    os.environ.get("MYRM_E2E_REAL_FRONTEND_STACK") != "1",
    reason="Set MYRM_E2E_REAL_FRONTEND_STACK=1 for real browser E2E",
)


async def _wait_health(base_url: str, timeout_s: float = 60.0) -> None:
    url = base_url + "/api/v1/health"
    deadline = asyncio.get_event_loop().time() + timeout_s
    last_err: str | None = None
    while asyncio.get_event_loop().time() < deadline:
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=5) as resp:
                if getattr(resp, "status", 200) == 200:
                    print(f"health_ok {url}")
                    return
        except urllib.error.HTTPError as exc:
            last_err = f"HTTP {exc.code}"
        except Exception as exc:
            last_err = str(exc)
        await asyncio.sleep(1)
    raise RuntimeError(f"health_failed {url} last={last_err}")


async def _open_preferences(page: Page) -> None:
    await page.goto(f"{FRONTEND_BASE}/settings/preferences", wait_until="domcontentloaded")
    await page.wait_for_load_state("load", timeout=15_000)


async def _assert_en_channel_sync_desc(page: Page) -> None:
    en_btn = page.get_by_role("button", name=re.compile(r"English|英文", re.I))
    if await en_btn.is_visible():
        await en_btn.click()
        await page.wait_for_timeout(800)
    desc = page.get_by_text(re.compile(r"Applies to the web interface", re.I))
    await desc.wait_for(state="visible", timeout=20_000)
    assert await desc.is_visible()
    print("ok_en_channel_sync_desc")


async def _assert_zh_channel_sync_desc(page: Page) -> None:
    zh_btn = page.get_by_role("button", name=re.compile(r"中文|Chinese", re.I))
    if await zh_btn.is_visible():
        await zh_btn.click()
        await page.wait_for_timeout(800)
    desc = page.get_by_text(re.compile(r"IM 渠道命令"))
    await desc.wait_for(state="visible", timeout=20_000)
    assert await desc.is_visible()
    print("ok_zh_channel_sync_desc")


async def _assert_locale_persisted_en() -> None:
    req = urllib.request.Request(f"{BACKEND_BASE}/api/v1/config/personalSettings", method="GET")
    with urllib.request.urlopen(req, timeout=10) as resp:
        body = json.loads(resp.read().decode())
    locale_val = (body.get("value") or {}).get("locale")
    assert locale_val in ("en", "en-US"), f"expected en locale, got {locale_val!r}"
    print(f"ok_locale_persisted {locale_val}")


async def run_real_channel_locale_flow() -> None:
    await _wait_health(BACKEND_BASE)
    await _wait_health(FRONTEND_BASE)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(locale="zh-CN")
        page = await context.new_page()
        try:
            await _open_preferences(page)
            await _assert_zh_channel_sync_desc(page)

            en_btn = page.get_by_role("button", name=re.compile(r"English|英文", re.I))
            await en_btn.click()
            await page.wait_for_timeout(1500)
            await _assert_en_channel_sync_desc(page)
            await _assert_locale_persisted_en()
        finally:
            await browser.close()


@pytest.mark.asyncio
async def test_real_channel_locale_preferences_flow() -> None:
    await run_real_channel_locale_flow()


def main() -> int:
    try:
        asyncio.run(run_real_channel_locale_flow())
    except Exception as exc:
        print(f"FAIL {exc}", file=sys.stderr)
        return 1
    print("PASS real_channel_locale_preferences_flow")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
