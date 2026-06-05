"""Real-stack frontend flow: configure providers from server `.env.test` (BASIC_* / LITE_*), defaults, chat smoke.

Read-only on `.env`. Requires frontend serving (default :3000) proxying to backend (:8080) and Patchright.

[manual]
    uv run python tests/e2e/real_frontend_provider_flow.py

[pytest — skipped unless MYRM_E2E_REAL_FRONTEND_STACK=1]
    MYRM_E2E_REAL_FRONTEND_STACK=1 uv run pytest tests/e2e/real_frontend_provider_flow.py -v
"""

from __future__ import annotations

import asyncio
import os
import re
import time
from pathlib import Path
from urllib.parse import urlparse

import pytest
from dotenv import load_dotenv
from patchright.async_api import Page, async_playwright

SERVER_ROOT = Path(__file__).resolve().parent.parent.parent


def _split_model(spec: str) -> tuple[str, str]:
    if "/" not in spec:
        return "", spec.strip()
    left, right = spec.split("/", 1)
    return left.strip(), right.strip()


async def _wait_health(base_url: str, timeout_s: float = 120.0) -> None:
    import urllib.error
    import urllib.request

    url = base_url.rstrip("/") + "/api/v1/health"
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


def _models_card(page: Page, model_id: str):
    models_panel = (
        page.locator("h4")
        .filter(has_text=re.compile(r"^(模型|MODELS|Models)$", re.I))
        .locator("xpath=ancestor::div[contains(@class,'space-y-4')][1]/div[contains(@class,'p-5')]")
        .first
    )
    return (
        models_panel.locator("div.rounded-xl.border")
        .filter(
            has=page.locator(
                "span.text-sm.font-medium",
                has_text=re.compile(rf"^{re.escape(model_id)}$"),
            )
        )
        .first
    )


async def _enable_model_toggle(page: Page, model_id: str) -> None:
    card = _models_card(page, model_id)
    await card.wait_for(state="visible", timeout=60_000)
    cls = await card.get_attribute("class") or ""
    if "border-primary/30" in cls:
        await page.wait_for_timeout(500)
        return

    await card.locator("button.relative.rounded-full").first.click()
    deadline = time.monotonic() + 120.0
    while time.monotonic() < deadline:
        card = _models_card(page, model_id)
        try:
            cls = await card.get_attribute("class", timeout=3_000) or ""
        except Exception:
            await asyncio.sleep(0.5)
            continue
        if "border-primary/30" in cls:
            await page.wait_for_timeout(500)
            return
        html = await card.inner_html()
        if "text-destructive" in html and ("IconAlert" in html or "alert" in html.lower()):
            raise RuntimeError((await card.inner_text())[:1600])
        await asyncio.sleep(0.5)

    body = await page.locator("body").inner_text()
    if re.search(r"已启用\s*1/|Enabled\s*1/", body):
        await page.wait_for_timeout(500)
        return

    raise TimeoutError(f"Timed out enabling model {model_id}")


async def _select_provider(page: Page, name: str) -> None:
    """Select a provider in the left sidebar list to show its config panel."""
    target = page.locator(f'[role="button"][aria-label="{name}"]').first
    await target.wait_for(state="visible", timeout=60_000)
    await target.scroll_into_view_if_needed()
    await target.click()
    await page.wait_for_timeout(600)
    await page.locator("h3", has_text=name).first.wait_for(state="visible", timeout=30_000)


async def _add_manual_model(page: Page, model_id: str) -> None:
    """Add a model via AddModelInput (two-step: expand input → fill → submit)."""
    existing = page.locator("span.text-sm.font-medium").filter(has_text=re.compile(rf"^{re.escape(model_id)}$"))
    if await existing.count() > 0:
        return

    models_panel = (
        page.locator("h4")
        .filter(has_text=re.compile(r"^(模型|MODELS|Models)$", re.I))
        .locator("xpath=ancestor::div[contains(@class,'space-y-4')][1]/div[contains(@class,'p-5')]")
        .first
    )
    await models_panel.wait_for(state="visible", timeout=30_000)
    await models_panel.scroll_into_view_if_needed()

    add_model_btn = (
        models_panel.locator("button")
        .filter(
            has=page.locator(
                "span.text-sm.font-medium",
                has_text=re.compile(r"^(添加模型|Add Model)$"),
            )
        )
        .first
    )
    await add_model_btn.wait_for(state="visible", timeout=30_000)
    await add_model_btn.click()

    model_input = models_panel.locator('input[placeholder*="gpt-4"], input[placeholder*="模型名称"]').first
    await model_input.wait_for(state="visible", timeout=15_000)
    await model_input.fill(model_id)
    await models_panel.locator("button").filter(has_text=re.compile(r"^(添加|Add)$")).first.click()

    await (
        page.locator("span.text-sm.font-medium")
        .filter(has_text=re.compile(rf"^{re.escape(model_id)}$"))
        .first.wait_for(state="visible", timeout=30_000)
    )
    await page.wait_for_timeout(400)


async def _dismiss_blocking_ui(page: Page) -> None:
    """Close toasts, dialogs, and alert overlays that block Playwright clicks."""
    await _emit_escape_burst(page, n=4)
    for name in ("跳过", "Skip for now", "Skip", "关闭", "Close", "确定", "OK"):
        btn = page.get_by_role("button", name=re.compile(re.escape(name), re.I))
        if await btn.count() == 0:
            continue
        try:
            if await btn.first.is_visible():
                await btn.first.click(timeout=2000)
                await page.wait_for_timeout(250)
        except Exception:
            pass


async def _emit_escape_burst(page: Page, n: int = 8) -> None:
    """Dismiss modal backdrops / nested dialogs that block the next UI interaction."""
    for _ in range(n):
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(220)


async def _ensure_provider_main_switch_on(page: Page, heading: str) -> None:
    """Turn on provider-level switch after at least one model is enabled."""
    h = page.locator("h3", has_text=heading).first
    await h.wait_for(state="visible", timeout=60_000)
    container = h.locator("xpath=ancestor::div[contains(@class,'justify-between')][1]")
    tgl = container.locator("button.relative.w-14.h-8").first
    await tgl.wait_for(state="visible", timeout=30_000)
    disabled = await tgl.get_attribute("disabled")
    if disabled is not None:
        return
    needs_click = await tgl.evaluate(
        """(btn) => {
          const thumb = btn.querySelector('div.rounded-full.bg-white');
          if (!thumb) return true;
          return !thumb.className.includes('left-7');
        }"""
    )
    if needs_click:
        await tgl.click()
        await page.wait_for_timeout(1500)


async def _add_custom_openai_like(
    page: Page,
    display_name: str,
    api_base_url: str,
    api_key: str,
    model_id: str,
) -> None:
    await page.get_by_role("button", name="添加提供商").click()
    dialog = page.get_by_role("dialog")
    await dialog.get_by_placeholder("如：MyCustomOpenAI").fill(display_name)
    await dialog.get_by_role("button", name="添加").click()
    await page.wait_for_timeout(800)

    await _select_provider(page, display_name)

    await page.get_by_placeholder("https://api.example.com/v1").fill(api_base_url.rstrip("/"))

    await _dismiss_blocking_ui(page)
    await page.locator("button.w-full.py-4").filter(has_text="添加").click(force=True)
    await page.locator('input[placeholder="sk-..."]').fill(api_key)
    await (
        page.locator("form")
        .filter(has=page.locator('input[placeholder="sk-..."]'))
        .get_by_role("button", name="添加")
        .click(force=True)
    )
    await page.wait_for_timeout(1000)
    await _emit_escape_burst(page, n=2)

    await _select_provider(page, display_name)
    await _add_manual_model(page, model_id)
    await _enable_model_toggle(page, model_id)
    await _ensure_provider_main_switch_on(page, display_name)


async def _configure_builtin_provider(page: Page, aria_name: str, api_key: str, model_id: str) -> None:
    target = page.locator(f'[role="button"][aria-label="{aria_name}"]').first
    await target.scroll_into_view_if_needed()
    await target.click()
    await page.wait_for_timeout(400)

    await page.locator("button.w-full.py-4").filter(has_text="添加").click(force=True)
    await page.locator('input[placeholder="sk-..."]').fill(api_key)
    await (
        page.locator("form")
        .filter(has=page.locator('input[placeholder="sk-..."]'))
        .get_by_role("button", name="添加")
        .click(force=True)
    )
    await page.wait_for_timeout(600)

    if await page.locator("span.text-sm.font-medium").filter(has_text=re.compile(rf"^{re.escape(model_id)}$")).count() == 0:
        await _add_manual_model(page, model_id)
        await page.wait_for_timeout(400)

    await _emit_escape_burst(page, n=3)

    await _enable_model_toggle(page, model_id)
    await _ensure_provider_main_switch_on(page, aria_name)


async def _pick_base_default(page: Page, model_id: str, provider_name: str) -> None:
    """Pick a single base default model from a specific provider (for chat smoke)."""
    blocks = page.locator("div.space-y-3").filter(has=page.locator("label", has_text="选择模型"))
    await blocks.first.wait_for(state="visible", timeout=120_000)
    trigger = blocks.first.locator("button").first
    await trigger.click()
    needle = model_id.split("/")[-1]
    inp = page.locator('input[placeholder="搜索模型..."]').locator("visible=true").first
    await inp.fill(needle)
    await page.wait_for_timeout(700)
    scroll = inp.locator('xpath=ancestor::div[contains(@class,"bg-popover")][1]/div[contains(@class,"max-h-64")]')
    btn = (
        scroll.locator("button")
        .filter(has_text=re.compile(re.escape(needle), re.I))
        .filter(has_text=re.compile(re.escape(provider_name), re.I))
        .first
    )
    await btn.click()
    pb = await blocks.first.locator("button").first.inner_text()
    if provider_name not in pb or needle.lower() not in pb.lower():
        raise RuntimeError(f"base_default_not_set pb={pb!r}")


async def _pick_default_models(
    page: Page,
    custom_display: str,
    basic_mid: str,
    lite_mid: str,
) -> None:
    blocks = page.locator("div.space-y-3").filter(has=page.locator("label", has_text="选择模型"))
    await blocks.first.wait_for(state="visible", timeout=120_000)
    await page.wait_for_timeout(1200)

    async def pick_nth(idx: int, want_suffix: str, provider_hint: str | None = None) -> None:
        trigger = blocks.nth(idx).locator("button").first
        await trigger.scroll_into_view_if_needed()
        await trigger.click()
        await page.wait_for_function(
            """(ph) => [...document.querySelectorAll('input')].some(
                (el) => el.placeholder === ph && el.offsetParent !== null
            )""",
            arg="搜索模型...",
            timeout=60_000,
        )
        needle = want_suffix.split("/")[-1]
        inp = page.locator('input[placeholder="搜索模型..."]').locator("visible=true").first
        await inp.fill("")
        if idx == 0:
            await inp.fill(needle)
        else:
            await inp.fill(needle.split("-")[-1])
        await page.wait_for_timeout(700)
        scroll = inp.locator('xpath=ancestor::div[contains(@class,"bg-popover")][1]/div[contains(@class,"max-h-64")]')
        await scroll.wait_for(state="visible", timeout=30_000)

        async def _pick_from_provider_group(group_label: str) -> None:
            header = scroll.locator("div.sticky").filter(has_text=re.compile(re.escape(group_label), re.I)).first
            await header.wait_for(state="visible", timeout=30_000)
            group = header.locator("xpath=ancestor::div[1]")
            model_btn = group.locator("button").filter(has_text=re.compile(rf"^{re.escape(needle)}$", re.I)).first
            await model_btn.scroll_into_view_if_needed()
            await model_btn.click()

        if provider_hint:
            await _pick_from_provider_group(provider_hint)
            btn = None
        elif idx == 2:
            await _pick_from_provider_group("MiniMax")
            btn = None
        else:
            btn = scroll.locator("button").filter(has_text=re.compile(rf"^{re.escape(needle)}$", re.I)).first
        try:
            if btn is not None:
                await btn.scroll_into_view_if_needed()
                await btn.click()
        except Exception as exc:
            try:
                excerpt = (await scroll.inner_text(timeout=5000))[:1200]
            except Exception:
                excerpt = await inp.evaluate("el => el.outerHTML.slice(0, 400)")
            raise RuntimeError(f"popover_pick_failed token={needle!r} excerpt={excerpt!r}") from exc
        await page.wait_for_timeout(500)

    await pick_nth(0, basic_mid, provider_hint=custom_display)
    await pick_nth(2, lite_mid)

    pb = await blocks.nth(0).locator("button").first.inner_text()
    pl = await blocks.nth(2).locator("button").first.inner_text()
    print("default_base_button=", pb)
    print("default_lite_button=", pl)
    needle_basic = basic_mid.split("/")[-1]
    needle_lite = lite_mid.split("/")[-1]
    flat_pb = " ".join(pb.split())
    if needle_basic.lower() not in flat_pb.lower():
        raise RuntimeError(f"base_default_not_set pb={pb!r}")
    if custom_display and custom_display not in flat_pb:
        # Popover may show openai-like label instead of custom display name.
        if "Xiaomi MiMo" in flat_pb:
            raise RuntimeError(f"base_default_wrong_provider pb={pb!r} want custom not Xiaomi")
    flat_pl = " ".join(pl.split())
    if "MiniMax" not in flat_pl or needle_lite.lower() not in flat_pl.lower():
        raise RuntimeError("lite_default_not_set")


async def _wait_assistant_markdown_contains_ok(page: Page, timeout_s: float = 120.0) -> None:
    """Require OK inside assistant Markdown; tolerate current MessageBox DOM."""
    deadline = time.monotonic() + timeout_s
    last_dump = ""
    while time.monotonic() < deadline:
        found, snap = await page.evaluate(
            """() => {
          const snippets = [];
          const proseNodes = document.querySelectorAll('[data-test-id="assistant-message"] .prose, .prose.max-w-none, .prose');
          for (const prose of proseNodes) {
            const raw = (prose.innerText || '').replace(/\\s+/g, ' ').trim();
            if (!raw) continue;
            snippets.push(raw.slice(0, 240));
            if (/\\bOK\\b/i.test(raw)) return [true, raw.slice(0, 500)];
            if (/401|Invalid API|invalid_key|Authentication/i.test(raw)) return ['auth', raw.slice(0, 500)];
          }
          const body = document.body.innerText || '';
          const chatPane = document.querySelector('[data-test-id="chat-messages"], main, [role="main"]');
          const chatText = chatPane ? (chatPane.innerText || '') : body;
          if (/无法连接到服务器|Failed to fetch/i.test(chatText)) return ['conn', chatText.slice(0, 500)];
          return [false, snippets.join(' | ').slice(0, 1200)];
        }"""
        )
        if found is True:
            return
        if found == "auth":
            raise RuntimeError(f"assistant_auth_error excerpt={snap[:800]!r}")
        if found == "conn":
            raise RuntimeError(f"frontend_connection_error excerpt={snap[:800]!r}")
        last_dump = str(snap)
        await asyncio.sleep(0.45)
    raise TimeoutError(f"assistant_markdown_no_OK excerpts={last_dump[:1600]!r}")


async def _select_chat_base_model(page: Page, provider_name: str, model_id: str) -> None:
    """Pick base model in the chat composer (agent mode may override settings default)."""
    needle = model_id.split("/")[-1]
    trigger = page.locator("button").filter(has_text=re.compile(re.escape(needle), re.I)).first
    if await trigger.count() == 0:
        trigger = page.locator("button").filter(has_text=re.compile(r"Gener\.\.\.|MiniMax|mimo", re.I)).first
    await trigger.click()
    inp = page.locator('input[placeholder="搜索模型..."]').locator("visible=true").first
    await inp.fill(needle)
    await page.wait_for_timeout(600)
    scroll = inp.locator('xpath=ancestor::div[contains(@class,"bg-popover")][1]/div[contains(@class,"max-h-64")]')
    header = scroll.locator("div.sticky").filter(has_text=re.compile(re.escape(provider_name), re.I)).first
    if await header.count() > 0:
        group = header.locator("xpath=ancestor::div[1]")
        btn = group.locator("button").filter(has_text=re.compile(rf"^{re.escape(needle)}$", re.I)).first
    else:
        btn = scroll.locator("button").filter(has_text=re.compile(rf"^{re.escape(needle)}$", re.I)).first
    await btn.click(force=True)
    await page.wait_for_timeout(400)


async def _chat_smoke(
    page: Page,
    chat_provider: str | None = None,
    chat_model: str | None = None,
    action_mode: str = "fast",
) -> str:
    await page.goto(
        os.environ.get("FRONTEND_URL", "http://127.0.0.1:3000").rstrip("/") + "/",
        timeout=120_000,
    )
    await page.wait_for_timeout(1500)
    await page.evaluate(
        """
        (mode) => {
          const c = JSON.parse(localStorage.getItem('securityConfig') || '{}');
          c.yoloModeEnabled = true;
          localStorage.setItem('securityConfig', JSON.stringify(c));
          localStorage.setItem('actionMode', mode);
        }
        """,
        action_mode,
    )
    await page.reload()
    await page.wait_for_timeout(2000)

    box = page.locator("textarea").first
    await box.wait_for(state="visible", timeout=60_000)
    if chat_provider and chat_model:
        await _select_chat_base_model(page, chat_provider, chat_model)
    await box.fill("Reply with exactly one word: OK")
    send = page.locator('button[aria-label="发送"], button[aria-label="Send"]')
    await send.click()

    stop_btn = page.locator('button[aria-label="Stop"]')
    try:
        await stop_btn.wait_for(state="visible", timeout=30_000)
        await stop_btn.wait_for(state="detached", timeout=180_000)
    except Exception:
        await page.wait_for_timeout(5000)

    await _wait_assistant_markdown_contains_ok(page, timeout_s=180.0)
    return "assistant_markdown_OK"


async def _resync_minimax_enabled_model(page: Page, lite_mid: str) -> None:
    """Force OFF→ON cycle so enabledModels / sync reliably updates before default-model page."""
    mid = lite_mid.split("/")[-1]
    await page.locator('[role="button"][aria-label="MiniMax"]').first.click()
    await page.wait_for_timeout(600)
    card = _models_card(page, mid)
    await card.wait_for(state="visible", timeout=60_000)
    cls = await card.get_attribute("class") or ""
    if "border-primary/30" in cls:
        await card.locator("button.relative.rounded-full").first.click()
        await page.wait_for_timeout(700)
    await _enable_model_toggle(page, mid)


async def main() -> None:
    load_dotenv(SERVER_ROOT / ".env", override=True)

    basic_kind, basic_mid = _split_model(os.environ["BASIC_MODEL"])
    _, lite_mid = _split_model(os.environ["LITE_MODEL"])
    if basic_kind.replace("-", "_") not in ("openai_like", "openai-like"):
        print("WARN: BASIC_MODEL prefix is not openai-like:", basic_kind)

    base_url = os.environ["BASIC_BASE_URL"]
    basic_key = os.environ["BASIC_API_KEY"]
    lite_key = os.environ["LITE_API_KEY"]

    frontend = os.environ.get("FRONTEND_URL", "http://127.0.0.1:3000")
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(Path.home() / "Library/Caches/ms-playwright"))

    await _wait_health(frontend)

    stamp = int(time.time())
    custom_name = f"E2E Basic {stamp}"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(locale="zh-CN")

        host = urlparse(frontend).hostname or "127.0.0.1"
        await context.add_cookies(
            [
                {
                    "name": "NEXT_LOCALE",
                    "value": "zh",
                    "domain": host,
                    "path": "/",
                }
            ]
        )
        page = await context.new_page()
        page.set_default_timeout(120_000)

        await page.goto(frontend.rstrip("/") + "/settings/models", timeout=120_000)
        await page.wait_for_timeout(4000)
        await _dismiss_blocking_ui(page)

        await _add_custom_openai_like(page, custom_name, base_url, basic_key, basic_mid)
        await _emit_escape_burst(page)
        await _ensure_provider_main_switch_on(page, custom_name)
        await _configure_builtin_provider(page, "MiniMax", lite_key, lite_mid)
        await _ensure_provider_main_switch_on(page, "MiniMax")

        await page.goto(frontend.rstrip("/") + "/settings/models", timeout=120_000)
        await page.wait_for_timeout(800)
        await _resync_minimax_enabled_model(page, lite_mid)
        await _ensure_provider_main_switch_on(page, "MiniMax")
        await page.wait_for_timeout(2500)

        await page.goto(frontend.rstrip("/") + "/settings/defaultModel", timeout=120_000)
        await page.wait_for_timeout(2500)
        await _pick_default_models(page, custom_name, basic_mid, lite_mid)

        chat_out = await _chat_smoke(page)
        print("chat_smoke_ok=", chat_out)

        await browser.close()


@pytest.mark.e2e
@pytest.mark.skipif(
    os.environ.get("MYRM_E2E_REAL_FRONTEND_STACK", "").strip() != "1",
    reason=(
        "Real frontend+backend stack E2E: set MYRM_E2E_REAL_FRONTEND_STACK=1 and "
        "configure myrm-agent-server/.env.test (BASIC_MODEL, BASIC_BASE_URL, BASIC_API_KEY, LITE_MODEL, LITE_API_KEY)."
    ),
)
@pytest.mark.asyncio
async def test_frontend_provider_defaults_and_chat_ok() -> None:
    await main()


if __name__ == "__main__":
    asyncio.run(main())
