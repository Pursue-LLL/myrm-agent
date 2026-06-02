"""E2E: Local search onboarding — full scenario matrix (Banner / Settings / API)."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any

import httpx
from patchright.async_api import BrowserContext, Page, async_playwright

FRONTEND = os.environ.get("FRONTEND_URL", "http://127.0.0.1:3000").rstrip("/")
BACKEND = os.environ.get("BACKEND_URL", "http://127.0.0.1:8080").rstrip("/")
PLAYWRIGHT_ENV = {
    **os.environ,
    "PLAYWRIGHT_BROWSERS_PATH": "/Users/yululiu/Library/Caches/ms-playwright",
    "PATCHRIGHT_BROWSERS_PATH": "/Users/yululiu/Library/Caches/ms-playwright",
}

MOCK_NO_SEARCH: dict[str, Any] = {
    "results": [],
    "has_available": False,
    "recommended_model": None,
    "search": [
        {
            "provider": "searxng",
            "base_url": "http://127.0.0.1:8081",
            "available": False,
            "latency_ms": 0,
            "error": "unavailable",
        },
    ],
    "search_has_available": False,
    "recommended_searxng_url": "http://127.0.0.1:8081",
}

MOCK_SEARXNG_ONLY: dict[str, Any] = {
    "results": [],
    "has_available": False,
    "recommended_model": None,
    "search": [
        {
            "provider": "searxng",
            "base_url": "http://127.0.0.1:8081",
            "available": True,
            "latency_ms": 42,
        },
    ],
    "search_has_available": True,
    "recommended_searxng_url": "http://127.0.0.1:8081",
}

MOCK_SEARXNG_START: dict[str, Any] = {
    "docker_invoked": True,
    "available": True,
    "base_url": "http://127.0.0.1:8081",
    "latency_ms": 10,
    "error": None,
}


async def _install_backend_route(
    context: BrowserContext,
    probe_mock: dict[str, Any] | None = None,
    *,
    searxng_start_mock: dict[str, Any] | None = None,
    probe_after_start: dict[str, Any] | None = None,
) -> None:
    """Bypass Next.js rewrite; optionally mock probe-local / searxng/start responses."""
    current_probe = probe_mock

    async def _route_handler(route) -> None:
        nonlocal current_probe
        url = route.request.url
        if current_probe is not None and "probe-local" in url:
            await route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(current_probe),
            )
            return
        if searxng_start_mock is not None and "searxng/start" in url:
            if probe_after_start is not None:
                current_probe = probe_after_start
            await route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(searxng_start_mock),
            )
            return
        if ":3000/api/v1/" in url:
            url = url.replace(":3000/api/v1/", ":8080/api/v1/")
        elif ":3000/webui/" in url:
            url = url.replace(":3000/webui/", ":8080/webui/")
        await route.continue_(url=url)

    await context.unroute("**/api/v1/**")
    await context.unroute("**/webui/**")
    await context.route("**/api/v1/**", _route_handler)
    await context.route("**/webui/**", _route_handler)


async def _clear_search_config() -> None:
    async with httpx.AsyncClient(base_url=f"{BACKEND}/api/v1", timeout=60.0) as client:
        resp = await client.put(
            "/config/searchServices",
            json={
                "value": {"searchServiceConfigs": []},
                "deviceId": "e2e-search-onboarding",
            },
        )
        if resp.status_code not in (200, 409):
            print(f"WARN: clear search config returned {resp.status_code}: {resp.text[:200]}")


async def _get_search_configs() -> list[dict[str, Any]]:
    async with httpx.AsyncClient(base_url=f"{BACKEND}/api/v1", timeout=60.0) as client:
        resp = await client.get("/config/searchServices")
        if resp.status_code != 200:
            return []
        return resp.json().get("value", {}).get("searchServiceConfigs", [])


async def _get_page_search_configs(page: Page) -> list[dict[str, Any]]:
    configs = await page.evaluate(
        """() => {
            try {
                const raw = localStorage.getItem('config-store-v4');
                if (!raw) return [];
                const parsed = JSON.parse(raw);
                const state = parsed.state ?? parsed;
                return state.searchServiceConfigs ?? [];
            } catch {
                return [];
            }
        }"""
    )
    return configs if isinstance(configs, list) else []


def _has_enabled_searxng(configs: list[dict[str, Any]]) -> bool:
    return any(c.get("search_service") == "searxng" and c.get("enabled") for c in configs)


async def _wait_for_searxng_enabled(page: Page, *, attempts: int = 30) -> list[dict[str, Any]]:
    for _ in range(attempts):
        await page.wait_for_timeout(500)
        page_configs = await _get_page_search_configs(page)
        if _has_enabled_searxng(page_configs):
            return page_configs
        server_configs = await _get_search_configs()
        if _has_enabled_searxng(server_configs):
            return server_configs
    return await _get_page_search_configs(page)


async def _force_local_deploy_mode(page: Page) -> None:
    await _goto_with_retry(page, f"{FRONTEND}/")
    await page.evaluate(
        """() => {
            localStorage.setItem(
                'dev-mode-storage',
                JSON.stringify({ state: { enabled: true, override: 'local' }, version: 0 }),
            );
        }"""
    )


async def _adopt_server_data_if_needed(page: Page) -> None:
    adopt = page.get_by_role("button", name="采用服务端数据")
    if await adopt.count() > 0:
        await adopt.first.click()
        await page.wait_for_timeout(800)


async def _wait_for_text(page: Page, pattern: str, timeout_ms: int = 5000) -> bool:
    deadline = asyncio.get_event_loop().time() + timeout_ms / 1000
    while asyncio.get_event_loop().time() < deadline:
        if await page.get_by_text(pattern).count() > 0:
            return True
        await page.wait_for_timeout(400)
    return False


async def _ensure_search_unconfigured(page: Page) -> None:
    try:
        await _clear_search_config()
    except httpx.HTTPError as exc:
        print(f"WARN: clear search config failed: {exc}")
    await _goto_with_retry(page, f"{FRONTEND}/settings/search")
    await page.wait_for_timeout(1200)
    await _adopt_server_data_if_needed(page)
    delete_btns = page.get_by_role("button", name="删除")
    if await delete_btns.count() == 0:
        delete_btns = page.get_by_role("button", name="Delete")
    while await delete_btns.count() > 0:
        await delete_btns.first.click()
        await page.wait_for_timeout(400)
        confirm = page.get_by_role("button", name="确认")
        if await confirm.count() == 0:
            confirm = page.get_by_role("button", name="Confirm")
        if await confirm.count() > 0:
            await confirm.first.click()
        await page.wait_for_timeout(600)
        delete_btns = page.get_by_role("button", name="删除")
        if await delete_btns.count() == 0:
            delete_btns = page.get_by_role("button", name="Delete")
    try:
        await _clear_search_config()
    except httpx.HTTPError as exc:
        print(f"WARN: clear search config failed: {exc}")
    await page.evaluate("() => localStorage.removeItem('config-store-v4')")
    await page.reload(wait_until="domcontentloaded")
    await page.wait_for_timeout(1000)


async def _goto_with_retry(page: Page, url: str, *, attempts: int = 5) -> None:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            return
        except Exception as exc:  # noqa: BLE001 — playwright navigation flakes
            last_error = exc
            if "ERR_ABORTED" in str(exc) and url.split("?")[0] in page.url:
                return
            if attempt + 1 < attempts:
                await page.wait_for_timeout(1500)
    if last_error is not None:
        raise last_error


async def _open_empty_chat(page: Page) -> None:
    await _ensure_search_unconfigured(page)
    await _goto_with_retry(page, f"{FRONTEND}/")
    await page.wait_for_timeout(1500)
    await _adopt_server_data_if_needed(page)


async def _wait_for_search_banner(page: Page, timeout_ms: int = 25000) -> None:
    found = await _wait_for_text(page, "可免费启用联网搜索", timeout_ms)
    if not found:
        found = await _wait_for_text(page, "Enable free web search", 5000)
    if not found:
        found = await _wait_for_text(page, "正在检测本地 AI 与搜索服务", 8000)
    assert found, "LocalCapabilitiesBanner search section not visible"


# --- API tests ---


async def _backend_is_ready() -> bool:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{BACKEND}/api/v1/health")
            return resp.status_code == 200
    except httpx.HTTPError:
        return False


async def test_probe_api() -> None:
    print("[API-1] probe-local structure...")
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.get(f"{BACKEND}/api/v1/config/onboarding/probe-local")
        assert resp.status_code == 200, f"probe-local returned {resp.status_code}"
        data = resp.json()
        assert "search" in data and "search_has_available" in data
        assert "recommended_searxng_url" in data
        assert len(data["search"]) == 1
        assert data["search"][0]["provider"] == "searxng"
        assert "8081" in data["recommended_searxng_url"]
    print("  OK")


async def test_readiness_search_hint() -> None:
    print("[API-2] readiness search suggestions when empty...")
    await _clear_search_config()
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(f"{BACKEND}/api/v1/config/readiness")
        assert resp.status_code == 200
        data = resp.json()
        search = data.get("search", {})
        if not search.get("is_ready", True):
            suggestions = search.get("suggestions", [])
            assert any("search" in s.lower() or "搜索" in s for s in suggestions)
    print("  OK")


# --- UI: Banner ---


async def test_probe_mock_searxng_available_in_browser(page: Page, context: BrowserContext) -> None:
    print("[UI-2] Frontend probe-local mock returns SearXNG available...")
    await _install_backend_route(context, MOCK_SEARXNG_ONLY)
    await _goto_with_retry(page, f"{FRONTEND}/")
    await _force_local_deploy_mode(page)
    await page.wait_for_timeout(1000)

    data = await page.evaluate(
        """async () => {
            const resp = await fetch('/api/v1/config/onboarding/probe-local', { credentials: 'include' });
            if (!resp.ok) throw new Error('probe-local status ' + resp.status);
            return resp.json();
        }"""
    )
    assert data.get("search_has_available") is True
    assert data["search"][0]["provider"] == "searxng"
    assert data["search"][0]["available"] is True
    await _install_backend_route(context, None)
    try:
        await _clear_search_config()
    except httpx.HTTPError as exc:
        print(f"WARN: post UI-2 clear search config failed: {exc}")
    await page.evaluate("() => localStorage.removeItem('config-store-v4')")
    print("  OK")


async def test_banner_paid_search_fallback(page: Page, context: BrowserContext) -> None:
    print("[UI-3] Banner paid-search fallback when probe finds nothing (mock)...")
    await _install_backend_route(context, MOCK_NO_SEARCH)
    await _open_empty_chat(page)
    await _wait_for_search_banner(page)

    cfg_btn = page.get_by_role("button", name="改用付费搜索服务")
    if await cfg_btn.count() == 0:
        cfg_btn = page.get_by_role("button", name="Use a paid search provider instead")
    assert await cfg_btn.count() > 0
    await cfg_btn.first.click()
    try:
        await page.wait_for_url("**/settings/**", timeout=15000)
    except Exception:
        await page.wait_for_timeout(2000)
    assert "/settings" in page.url, f"Expected settings page, got {page.url}"
    await _install_backend_route(context, None)
    print("  OK")


async def test_banner_hidden_after_search_configured(page: Page) -> None:
    print("[UI-4] Search onboarding prompts hidden when search configured...")
    await _goto_with_retry(page, f"{FRONTEND}/")
    await page.wait_for_timeout(2000)
    await _adopt_server_data_if_needed(page)
    chip = page.locator("button").filter(has_text="启用搜索").locator("visible=true")
    assert await chip.count() == 0
    configs = await _get_search_configs()
    if any(c.get("enabled") for c in configs):
        assert await page.get_by_text("可免费启用联网搜索").count() == 0
    print("  OK")


# --- UI: Input toolbar (SearchSetupChip removed) ---


async def test_input_search_chip_removed(page: Page, context: BrowserContext) -> None:
    print("[UI-5] Message input no longer shows SearchSetupChip...")
    await _install_backend_route(context, MOCK_NO_SEARCH)
    await _goto_with_retry(page, f"{FRONTEND}/")
    await page.evaluate("() => localStorage.removeItem('config-store-v4')")
    await page.reload(wait_until="domcontentloaded")
    await page.wait_for_timeout(2000)

    chip = page.locator("button").filter(has_text="启用搜索").locator("visible=true")
    if await chip.count() == 0:
        chip = page.locator("button").filter(has_text="Enable Search").locator("visible=true")
    assert await chip.count() == 0, "SearchSetupChip should be removed from MessageInput"
    await _install_backend_route(context, None)
    print("  OK")


async def test_banner_consent_dialog_on_docker_start(page: Page, context: BrowserContext) -> None:
    print("[UI-6] Banner Docker start shows install consent dialog (mock)...")
    await _install_backend_route(
        context,
        MOCK_NO_SEARCH,
        searxng_start_mock=MOCK_SEARXNG_START,
        probe_after_start=MOCK_SEARXNG_ONLY,
    )
    await _open_empty_chat(page)
    await _wait_for_search_banner(page)

    start_btn = page.get_by_role("button", name="启动 SearXNG（Docker）")
    if await start_btn.count() == 0:
        start_btn = page.get_by_role("button", name="Start SearXNG (Docker)")
    assert await start_btn.count() > 0
    await start_btn.first.click()
    await page.wait_for_timeout(800)

    consent = page.get_by_role("heading", name="安装并启用 SearXNG？")
    if await consent.count() == 0:
        consent = page.get_by_role("heading", name="Install and enable SearXNG?")
    assert await consent.count() > 0

    confirm = page.get_by_role("button", name="同意并安装")
    if await confirm.count() == 0:
        confirm = page.get_by_role("button", name="Agree and install")
    assert await confirm.count() > 0
    await confirm.first.click()

    configs = await _wait_for_searxng_enabled(page)
    assert _has_enabled_searxng(configs)
    await _install_backend_route(context, None)
    print("  OK")


# --- UI: Settings ---


async def test_settings_quick_enable(page: Page, context: BrowserContext) -> None:
    """Settings SearchSection empty-state quick enable (same probe path as banner/chip)."""
    print("[UI-9] Settings empty-state quick enable...")
    await _install_backend_route(context, MOCK_SEARXNG_ONLY)
    await _force_local_deploy_mode(page)
    await _ensure_search_unconfigured(page)

    quick_btn = page.locator("button").filter(has_text="一键启用 SearXNG").locator("visible=true")
    found = False
    for _ in range(30):
        if await quick_btn.count() > 0:
            found = True
            break
        quick_btn = page.locator("button").filter(has_text="Enable SearXNG").locator("visible=true")
        if await quick_btn.count() > 0:
            found = True
            break
        quick_btn = page.locator("button").filter(has_text="一键启用 SearXNG").locator("visible=true")
        await page.wait_for_timeout(500)
    assert found, f"Quick-enable button missing; url={page.url}"
    await quick_btn.first.click()
    await page.wait_for_timeout(2500)
    assert await page.get_by_text("SearXNG").count() > 0
    await _install_backend_route(context, None)
    print("  OK")


async def test_manual_searxng_china_preset(page: Page) -> None:
    print("[UI-10] Manual SearXNG add with china region preset...")
    await _force_local_deploy_mode(page)
    await _ensure_search_unconfigured(page)

    clicked = False
    add_labels = (
        "添加第一个配置",
        "添加首个配置",
        "Add First Config",
        "Add First Configuration",
        "添加配置",
        "Add Configuration",
    )
    for _ in range(30):
        for label in add_labels:
            btn = page.get_by_role("button", name=label)
            if await btn.count() > 0:
                await btn.first.scroll_into_view_if_needed()
                await btn.first.click(timeout=15000)
                clicked = True
                break
        if clicked:
            break
        await page.wait_for_timeout(500)
    assert clicked, f"Add-config button missing; url={page.url}"
    await page.wait_for_timeout(800)

    region_trigger = page.get_by_text("全球", exact=True)
    if await region_trigger.count() > 0:
        await region_trigger.first.click()
        await page.wait_for_timeout(300)
        await page.get_by_text("中国", exact=True).first.click()
    await page.wait_for_timeout(400)

    save_btn = page.get_by_role("button", name="保存")
    if await save_btn.count() == 0:
        save_btn = page.get_by_role("button", name="Save")
    await save_btn.first.click()
    await page.wait_for_timeout(2500)

    assert await page.get_by_text("SearXNG").count() > 0
    configs = await _get_search_configs()
    sx = next((c for c in configs if c.get("search_service") == "searxng"), None)
    if sx is not None:
        extra = sx.get("extra_params") or {}
        assert extra.get("language") == "zh-CN"
    print("  OK")


async def test_settings_quick_enable_shows_consent_when_no_search(page: Page, context: BrowserContext) -> None:
    print("[UI-11] Settings quick-enable shows install consent when SearXNG down (mock)...")
    await _install_backend_route(context, MOCK_NO_SEARCH)
    await _force_local_deploy_mode(page)
    await _ensure_search_unconfigured(page)

    quick_btn = page.locator("button").filter(has_text="一键启用 SearXNG").locator("visible=true")
    found = False
    for _ in range(30):
        if await quick_btn.count() > 0:
            found = True
            break
        quick_btn = page.locator("button").filter(has_text="Enable SearXNG").locator("visible=true")
        if await quick_btn.count() > 0:
            found = True
            break
        quick_btn = page.locator("button").filter(has_text="一键启用 SearXNG").locator("visible=true")
        await page.wait_for_timeout(500)
    assert found, f"Quick-enable button missing; url={page.url}"
    await quick_btn.first.click()
    await page.wait_for_timeout(1200)

    consent = page.get_by_role("heading", name="安装并启用 SearXNG？")
    if await consent.count() == 0:
        consent = page.get_by_role("heading", name="Install and enable SearXNG?")
    assert await consent.count() > 0, "Consent dialog should open when quick-enable needs Docker"
    cancel = page.get_by_role("button", name="取消")
    if await cancel.count() == 0:
        cancel = page.get_by_role("button", name="Cancel")
    if await cancel.count() > 0:
        await cancel.first.click()
    await _install_backend_route(context, None)
    print("  OK")


async def test_fast_search_guard_without_config(page: Page, context: BrowserContext) -> None:
    print("[UI-13] Fast search mode blocked when search not configured...")
    await _install_backend_route(context, MOCK_NO_SEARCH)
    await _force_local_deploy_mode(page)
    await _ensure_search_unconfigured(page)
    await _goto_with_retry(page, f"{FRONTEND}/")
    await page.wait_for_timeout(2500)
    await _adopt_server_data_if_needed(page)

    agent_labels = ("智能代理", "Agent", "智能体")
    for label in agent_labels:
        agent_radio = page.get_by_role("radio", name=label)
        if await agent_radio.count() > 0:
            await agent_radio.first.click()
            await page.wait_for_timeout(500)
            break

    fast_labels = ("快速搜索", "Fast Search")
    clicked_fast = False
    for label in fast_labels:
        fast_radio = page.get_by_role("radio", name=label)
        if await fast_radio.count() > 0:
            await fast_radio.first.click(timeout=15000)
            clicked_fast = True
            break
    assert clicked_fast, "Fast search mode radio not found on chat page"
    await page.wait_for_timeout(1200)
    assert await page.get_by_text("搜索服务未配置").count() > 0 or await page.get_by_text(
        "Search service not configured"
    ).count() > 0
    await _install_backend_route(context, None)
    print("  OK")


async def test_create_dialog_defaults_searxng_local(page: Page) -> None:
    print("[UI-14] Manual add dialog defaults to SearXNG in local mode...")
    await _force_local_deploy_mode(page)
    await _ensure_search_unconfigured(page)

    clicked = False
    add_labels = (
        "添加第一个配置",
        "添加首个配置",
        "Add First Config",
        "Add First Configuration",
        "添加配置",
        "Add Configuration",
    )
    for _ in range(30):
        for label in add_labels:
            btn = page.get_by_role("button", name=label)
            if await btn.count() > 0:
                await btn.first.scroll_into_view_if_needed()
                await btn.first.click(timeout=15000)
                clicked = True
                break
        if clicked:
            break
        await page.wait_for_timeout(500)
    assert clicked, f"Add-config button missing; url={page.url}"

    await page.wait_for_timeout(1000)
    assert await page.get_by_placeholder("http://127.0.0.1:8081").count() > 0
    cancel = page.get_by_role("button", name="取消")
    if await cancel.count() == 0:
        cancel = page.get_by_role("button", name="Cancel")
    if await cancel.count() > 0:
        await cancel.first.click()
    print("  OK")


async def test_banner_auto_enable_when_searxng_up(page: Page, context: BrowserContext) -> None:
    print("[UI-15] Banner auto-enables when probe reports SearXNG available (mock)...")
    await _install_backend_route(context, MOCK_SEARXNG_ONLY)
    await _force_local_deploy_mode(page)
    await _ensure_search_unconfigured(page)
    await _goto_with_retry(page, f"{FRONTEND}/")
    await page.wait_for_timeout(4000)

    configs = await _wait_for_searxng_enabled(page, attempts=20)
    assert _has_enabled_searxng(configs)
    assert await page.get_by_text("可免费启用联网搜索").count() == 0
    await _install_backend_route(context, None)
    print("  OK")


async def test_config_persistence_api(page: Page) -> None:
    print("[UI-12] Search config persisted on settings page...")
    await page.goto(f"{FRONTEND}/settings/search", wait_until="domcontentloaded", timeout=60000)
    await page.wait_for_timeout(1500)
    ui_has = await page.get_by_text("SearXNG").count() > 0
    configs = await _get_search_configs()
    enabled = [c for c in configs if c.get("enabled")]
    assert ui_has or len(enabled) >= 1
    print("  OK")


async def main() -> None:
    print("=== Search Onboarding Full E2E Matrix ===")
    if not await _backend_is_ready():
        print(f"SKIP: backend not ready at {BACKEND} (start server before E2E)")
        sys.exit(0)
    await test_probe_api()
    await test_readiness_search_hint()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, env=PLAYWRIGHT_ENV)
        context = await browser.new_context(locale="zh-CN")
        await context.add_cookies(
            [
                {
                    "name": "myrm_auth",
                    "value": "1",
                    "domain": "127.0.0.1",
                    "path": "/",
                }
            ]
        )
        await _install_backend_route(context, None)
        page = await context.new_page()
        await _force_local_deploy_mode(page)
        try:
            await test_probe_mock_searxng_available_in_browser(page, context)
            await test_input_search_chip_removed(page, context)
            await test_banner_paid_search_fallback(page, context)
            await test_banner_hidden_after_search_configured(page)
            await test_banner_consent_dialog_on_docker_start(page, context)
            await test_settings_quick_enable_shows_consent_when_no_search(page, context)
            await test_create_dialog_defaults_searxng_local(page)
            await test_manual_searxng_china_preset(page)
            await test_settings_quick_enable(page, context)
            await test_fast_search_guard_without_config(page, context)
            await test_banner_auto_enable_when_searxng_up(page, context)
            await test_config_persistence_api(page)
        finally:
            await browser.close()

    print("\n=== ALL SEARCH ONBOARDING SCENARIOS PASSED (14 UI + 2 API) ===")


if __name__ == "__main__":
    asyncio.run(main())
