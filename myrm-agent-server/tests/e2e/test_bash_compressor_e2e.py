"""E2E: declarative bash output compression in a real chat session.

Requires frontend (:3000) proxying to backend (:8080). Reads myrm-agent-server/.env
(BASIC_*, LITE_*) and configures providers via the settings UI like a real user.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

import httpx
import pytest
from dotenv import load_dotenv
from myrm_agent_harness.agent.meta_tools.bash.output_compressor import compress_output
from patchright.async_api import Page, async_playwright

SERVER_ROOT = Path(__file__).resolve().parent.parent.parent
WORKSPACES_ROOT = Path.home() / ".myrm/harness/workspaces"
BASE_URL = os.environ.get("FRONTEND_URL", "http://127.0.0.1:3000").rstrip("/")
BACKEND_URL = os.environ.get("BACKEND_URL", "http://127.0.0.1:8080").rstrip("/")
SCREENSHOTS_DIR = Path(__file__).parent / "screenshots"

SSE_CAPTURE_SCRIPT = """
() => {
  if (window.__e2eSseCaptureInstalled) return;
  window.__e2eSseCaptureInstalled = true;
  window.__e2eSseEvents = [];
  const origFetch = window.fetch;
  window.fetch = async function (...args) {
    const response = await origFetch.apply(this, args);
    const url = typeof args[0] === 'string' ? args[0] : args[0]?.url || '';
    if (!url.includes('agent-stream')) {
      return response;
    }
    const clone = response.clone();
    void (async () => {
      const reader = clone.body?.getReader();
      if (!reader) return;
      const decoder = new TextDecoder();
      let buffer = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\\n');
        buffer = lines.pop() || '';
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          try {
            window.__e2eSseEvents.push(JSON.parse(line.slice(6)));
          } catch {
            /* ignore malformed SSE chunks */
          }
        }
      }
    })();
    return response;
  };
}
"""


async def _goto_with_retry(
    page: Page,
    url: str,
    *,
    timeout_ms: int = 120_000,
    attempts: int = 5,
) -> None:
    last_err: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            await page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
            return
        except Exception as exc:
            last_err = exc
            print(f"goto_retry {attempt}/{attempts} {url}: {exc}")
            await asyncio.sleep(2 * attempt)
    raise RuntimeError(f"goto_failed {url}") from last_err


async def _wait_stack_ready(frontend_url: str, timeout_s: float = 120.0) -> None:
    """Wait until frontend and proxied backend health respond."""
    health_url = frontend_url.rstrip("/") + "/api/v1/health"
    home_url = frontend_url.rstrip("/") + "/"
    deadline = time.monotonic() + timeout_s
    last_err: str | None = None
    while time.monotonic() < deadline:
        for url in (health_url, home_url):
            try:
                req = urllib.request.Request(url, method="GET")
                with urllib.request.urlopen(req, timeout=10) as resp:
                    if getattr(resp, "status", 200) == 200:
                        last_err = None
                        continue
                    last_err = f"{url} HTTP {getattr(resp, 'status', '?')}"
            except urllib.error.HTTPError as exc:
                last_err = f"{url} HTTP {exc.code}"
            except Exception as exc:
                last_err = f"{url} {exc}"
                break
        else:
            print(f"stack_ready {frontend_url}")
            return
        await asyncio.sleep(1.5)
    raise RuntimeError(f"stack_not_ready last={last_err}")


def _split_model(spec: str) -> tuple[str, str]:
    if "/" not in spec:
        return "", spec.strip()
    left, right = spec.split("/", 1)
    return left.strip(), right.strip()


async def _emit_escape_burst(page: Page, n: int = 6) -> None:
    for _ in range(n):
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(200)


async def _apply_tauri_dev_mode(page: Page) -> None:
    """Set tauri dev override after a real document exists (init_script breaks Playwright goto)."""
    await page.evaluate(
        """() => {
          localStorage.setItem(
            'dev-mode-storage',
            JSON.stringify({ state: { enabled: true, override: 'tauri' }, version: 0 })
          );
        }"""
    )


async def _dismiss_conflict_dialog(page: Page) -> None:
    try:
        btn = page.locator('button:has-text("保留本地修改"), button:has-text("采用服务端数据")').first
        if await btn.count() > 0:
            await btn.click(force=True)
            await page.wait_for_timeout(400)
    except Exception:
        pass


async def _ensure_provider_main_switch_on(page: Page, heading: str) -> None:
    h = page.locator("h3", has_text=heading).first
    await h.wait_for(state="visible", timeout=60_000)
    container = h.locator("xpath=ancestor::div[contains(@class,'justify-between')][1]")
    tgl = container.locator("button.relative.w-14.h-8").first
    needs_click = await tgl.evaluate(
        """(btn) => {
          const thumb = btn.querySelector('div.rounded-full.bg-white');
          if (!thumb) return true;
          return !thumb.className.includes('left-7');
        }"""
    )
    if needs_click:
        await tgl.click()
        await page.wait_for_timeout(1200)


def _model_row(page: Page, model_id: str):
    return (
        page.locator("span.text-sm.font-medium")
        .filter(has_text=re.compile(rf"^{re.escape(model_id)}$"))
        .first.locator(
            "xpath=ancestor::div["
            'contains(@class,"rounded-xl") and contains(@class,"border") '
            'and contains(@class,"flex-col") and contains(@class,"gap-2")'
            "]"
        )
        .first
    )


async def _add_custom_openai_like(
    page: Page,
    display_name: str,
    api_base_url: str,
    api_key: str,
    model_id: str,
) -> None:
    await page.get_by_role("button", name=re.compile(r"添加提供商|Add Provider")).click()
    dialog = page.get_by_role("dialog")
    await dialog.get_by_placeholder(re.compile(r"MyCustom|如")).fill(display_name)
    await dialog.get_by_role("button", name=re.compile(r"^添加$|^Add$")).click()
    await page.wait_for_timeout(800)

    await page.get_by_placeholder(re.compile(r"https://api")).fill(api_base_url.rstrip("/"))

    await page.locator("button.w-full.py-4").filter(has_text=re.compile(r"添加|Add")).click()
    await page.locator('input[placeholder="sk-..."]').fill(api_key)
    await (
        page.locator("form")
        .filter(has=page.locator('input[placeholder="sk-..."]'))
        .get_by_role("button", name=re.compile(r"添加|Add"))
        .click()
    )
    await page.wait_for_timeout(600)

    await page.get_by_role("button", name=re.compile(r"添加模型|Add Model")).click()
    row = page.locator("div.flex.gap-2").filter(has=page.locator('input[placeholder*="模型名称"], input[placeholder*="gpt-4"]'))
    await row.locator('input[placeholder*="模型名称"], input[placeholder*="gpt-4"]').fill(model_id)
    await row.get_by_role("button", name=re.compile(r"^添加$|^Add$")).click()

    card = _model_row(page, model_id)
    cls = await card.get_attribute("class") or ""
    if "border-primary/30" not in cls:
        await card.locator("button.relative.rounded-full").first.click()
        await _await_toggle_validate(card)


async def _configure_builtin_provider(page: Page, aria_name: str, api_key: str, model_id: str) -> None:
    target = page.locator(f'[role="button"][aria-label="{aria_name}"]').first
    await target.scroll_into_view_if_needed()
    await target.click()
    await page.wait_for_timeout(400)

    add_key = page.locator("button.w-full.py-4").filter(has_text=re.compile(r"添加|Add"))
    if await add_key.count() > 0:
        await add_key.click()
        await page.locator('input[placeholder="sk-..."]').fill(api_key)
        await (
            page.locator("form")
            .filter(has=page.locator('input[placeholder="sk-..."]'))
            .get_by_role("button", name=re.compile(r"添加|Add"))
            .click()
        )
        await page.wait_for_timeout(600)

    if await page.locator("span.text-sm.font-medium").filter(has_text=re.compile(rf"^{re.escape(model_id)}$")).count() == 0:
        await page.get_by_role("button", name=re.compile(r"添加模型|Add Model")).click()
        row = page.locator("div.flex.gap-2").filter(
            has=page.locator('input[placeholder*="模型名称"], input[placeholder*="gpt-4"]')
        )
        await row.locator('input[placeholder*="模型名称"], input[placeholder*="gpt-4"]').fill(model_id)
        await row.get_by_role("button", name=re.compile(r"^添加$|^Add$")).click()
        await page.wait_for_timeout(400)

    await _emit_escape_burst(page, n=3)
    card = _model_row(page, model_id)
    cls = await card.get_attribute("class") or ""
    if "border-primary/30" not in cls:
        await card.locator("button.relative.rounded-full").first.click()
        await _await_toggle_validate(card)


async def _await_toggle_validate(card, timeout_s: float = 180.0) -> None:
    deadline = time.monotonic() + timeout_s
    last_txt = ""
    while time.monotonic() < deadline:
        cls = await card.get_attribute("class") or ""
        if "border-primary/30" in cls:
            return
        html = await card.evaluate("el => el.innerHTML")
        if "text-green-600" in html:
            return
        if "text-destructive" in html and "lucide-alert" in html:
            last_txt = await card.inner_text()
            raise RuntimeError(last_txt[:1600])
        await asyncio.sleep(0.35)
    last_txt = await card.inner_text()
    raise TimeoutError(last_txt[:1600])


async def _resync_minimax_enabled_model(page: Page, lite_mid: str) -> None:
    mid = lite_mid.split("/")[-1]
    await page.locator('[role="button"][aria-label="MiniMax"]').first.click()
    await page.wait_for_timeout(600)
    card = _model_row(page, mid)
    cls = await card.get_attribute("class") or ""
    toggle = card.locator("button.relative.rounded-full").first
    if "border-primary/30" in cls:
        await toggle.click()
        await page.wait_for_timeout(700)
    await toggle.click()
    await _await_toggle_validate(card)


def _probe_model_selection_works(selection: dict[str, object]) -> bool:
    """Quick auth probe: True when agent-stream accepts the model selection."""
    payload = {
        "messageId": f"probe-{uuid.uuid4().hex[:8]}",
        "query": "Reply with exactly: PROBE_OK",
        "modelSelection": selection,
        "actionMode": "agent",
        "memoryRequireConfirmation": False,
        "enableMemoryAutoExtraction": False,
    }
    try:
        with httpx.Client(base_url=BACKEND_URL, timeout=90.0) as client:
            with client.stream(
                "POST",
                "/api/v1/agents/agent-stream",
                json=payload,
                timeout=90.0,
            ) as resp:
                if resp.status_code != 200:
                    return False
                for line in resp.iter_lines():
                    if not line.startswith("data: "):
                        continue
                    try:
                        event = json.loads(line[6:])
                    except json.JSONDecodeError:
                        continue
                    if not event:
                        continue
                    event_type = event.get("type")
                    if event_type == "error":
                        err = str(event.get("error", ""))
                        if any(
                            token in err
                            for token in (
                                "Invalid API Key",
                                "401",
                                "Authentication",
                                "auth_permanent",
                            )
                        ):
                            return False
                    if event_type in ("message", "reasoning", "tool_stdout_chunk"):
                        data = event.get("data")
                        if data:
                            return True
                    if event_type == "message_end":
                        return True
    except Exception as exc:
        print(f"[probe] model probe error: {exc}")
        return False
    return False


def _resolve_working_base_selection() -> dict[str, object]:
    from tests.api.agent.utils import get_lite_model_selection, get_model_selection

    for label, getter in (
        ("BASIC", get_model_selection),
        ("LITE", get_lite_model_selection),
    ):
        try:
            selection = getter()
        except Exception as exc:
            print(f"[probe] skip {label}: {exc}")
            continue
        if _probe_model_selection_works(selection):
            print(f"[probe] using {label} model {selection.get('providerId')}/{selection.get('model')}")
            return selection
        print(f"[probe] {label} model auth failed, trying next")
    raise RuntimeError("No working model API key in .env.test (probed BASIC_MODEL and LITE_MODEL)")


def _patch_provider_entry(
    providers: list[dict[str, object]],
    *,
    provider_id: str,
    api_key: str,
    api_url: str,
    model_name: str,
) -> None:
    for provider in providers:
        if provider.get("id") != provider_id:
            continue
        provider["isEnabled"] = True
        if api_url:
            provider["apiUrl"] = api_url
        provider["apiKeys"] = [
            {
                "id": f"e2e_{int(time.time())}",
                "key": api_key,
                "remark": "E2E",
                "isActive": True,
            }
        ]
        enabled = set(provider.get("enabledModels") or [])
        available = set(provider.get("availableModels") or [])
        enabled.add(model_name)
        available.add(model_name)
        provider["enabledModels"] = sorted(enabled)
        provider["availableModels"] = sorted(available)
        return
    raise RuntimeError(f"Provider {provider_id} not found in config")


def _sync_providers_and_defaults_from_env() -> dict[str, object]:
    """Sync providers + default models to backend (avoids flaky default-model popover)."""
    load_dotenv(SERVER_ROOT / ".env", override=True)
    working = _resolve_working_base_selection()
    basic_mid = os.environ.get("BASIC_MODEL", "openai-like/mimo-v2.5-pro")
    lite_mid = os.environ.get("LITE_MODEL", "minimax/MiniMax-M2.7")
    basic_pid, basic_name = _split_model(basic_mid)
    lite_pid, lite_name = _split_model(lite_mid)
    work_pid = str(working.get("providerId", basic_pid))
    work_name = str(working.get("model", basic_name)).split("/")[-1]
    if not basic_pid:
        basic_pid = "openai-like"
    if not lite_pid:
        lite_pid = "minimax"

    basic_key = os.environ.get("BASIC_API_KEY", "").strip()
    lite_key = os.environ.get("LITE_API_KEY", "").strip()
    basic_url = os.environ.get("BASIC_BASE_URL", "").strip()
    lite_url = os.environ.get("LITE_BASE_URL", "").strip()

    with httpx.Client(base_url=BACKEND_URL, timeout=30.0) as client:
        prov_resp = client.get("/api/v1/config/providers")
        prov_resp.raise_for_status()
        prov_body = prov_resp.json()
        prov_value = dict(prov_body.get("value") or {})
        providers = list(prov_value.get("providers") or [])

        if basic_pid.replace("-", "_") in ("openai_like", "openailike"):
            custom_id = f"e2e_basic_{int(time.time())}"
            providers.append(
                {
                    "id": custom_id,
                    "name": custom_id,
                    "isBuiltIn": False,
                    "isEnabled": True,
                    "apiUrl": basic_url,
                    "apiKeys": [
                        {
                            "id": "e2e_key",
                            "key": basic_key,
                            "remark": "E2E",
                            "isActive": True,
                        }
                    ],
                    "enabledModels": [basic_name],
                    "availableModels": [basic_name],
                }
            )
            basic_pid = custom_id
        else:
            _patch_provider_entry(
                providers,
                provider_id=basic_pid.replace("-", "_"),
                api_key=basic_key,
                api_url=basic_url,
                model_name=basic_name,
            )

        _patch_provider_entry(
            providers,
            provider_id=lite_pid.replace("-", "_"),
            api_key=lite_key,
            api_url=lite_url,
            model_name=lite_name,
        )

        prov_value["providers"] = providers
        prov_value["defaultModelConfig"] = {
            "baseModel": {
                "primary": {
                    "providerId": work_pid.replace("-", "_"),
                    "model": work_name,
                }
            },
            "liteModel": {
                "primary": {
                    "providerId": lite_pid.replace("-", "_"),
                    "model": lite_name,
                }
            },
        }

        dm_resp = client.get("/api/v1/config/defaultModelConfig")
        dm_version = dm_resp.json().get("version") if dm_resp.status_code == 200 else None

        changes: list[dict[str, object]] = [
            {
                "key": "providers",
                "value": prov_value,
                "expectedVersion": prov_body.get("version"),
                "timestamp": int(time.time() * 1000),
            }
        ]
        if dm_version is not None:
            changes.append(
                {
                    "key": "defaultModelConfig",
                    "value": prov_value["defaultModelConfig"],
                    "expectedVersion": dm_version,
                    "timestamp": int(time.time() * 1000),
                }
            )

        sync_resp = client.post(
            "/api/v1/config/sync",
            json={"changes": changes, "deviceId": "bash-compressor-e2e"},
        )
        sync_resp.raise_for_status()
    print("[配置] 已通过 API 同步 providers + defaultModelConfig")
    return working


async def _pick_default_models(page: Page, basic_mid: str, lite_mid: str) -> None:
    blocks = page.locator("div.space-y-3").filter(has=page.locator("label", has_text=re.compile(r"选择模型|Select")))
    await blocks.first.wait_for(state="visible", timeout=120_000)
    await page.wait_for_timeout(1200)

    async def pick_nth(idx: int, want_suffix: str) -> None:
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
        search_token = needle if idx == 0 else "MiniMax"
        await inp.fill(search_token)
        await page.wait_for_timeout(700)
        scroll = inp.locator('xpath=ancestor::div[contains(@class,"bg-popover")][1]/div[contains(@class,"max-h-64")]')
        await scroll.wait_for(state="visible", timeout=30_000)
        btn = scroll.locator("button").filter(has_text=re.compile(re.escape(needle), re.I)).first
        try:
            await btn.scroll_into_view_if_needed()
            await btn.click()
        except Exception as exc:
            try:
                excerpt = (await scroll.inner_text(timeout=5000))[:1200]
            except Exception:
                excerpt = await inp.evaluate("el => el.outerHTML.slice(0, 400)")
            raise RuntimeError(f"popover_pick_failed token={needle!r} excerpt={excerpt!r}") from exc
        await page.wait_for_timeout(500)

    await pick_nth(0, basic_mid)
    await pick_nth(2, lite_mid)


async def setup_models_from_env(page: Page) -> None:
    load_dotenv(SERVER_ROOT / ".env", override=True)
    _sync_providers_and_defaults_from_env()

    basic_kind, basic_mid = _split_model(os.environ.get("BASIC_MODEL", "openai-like/mimo-v2.5-pro"))
    _, lite_mid = _split_model(os.environ.get("LITE_MODEL", "minimax/MiniMax-M2.7"))
    basic_base = os.environ.get("BASIC_BASE_URL", "").strip()
    basic_key = os.environ.get("BASIC_API_KEY", "").strip()
    lite_key = os.environ.get("LITE_API_KEY", "").strip()

    if not basic_key or not lite_key:
        raise RuntimeError("BASIC_API_KEY and LITE_API_KEY must be set in myrm-agent-server/.env.test")

    stamp = int(time.time())
    custom_name = f"E2E Basic {stamp}"

    print("\n[配置] 打开模型服务设置...")
    await _goto_with_retry(page, BASE_URL)
    await _apply_tauri_dev_mode(page)
    await _goto_with_retry(page, f"{BASE_URL}/settings/models")
    await page.wait_for_timeout(4000)
    await _dismiss_conflict_dialog(page)

    # 等待 ProviderList 加载完成（骨架屏消失）
    await page.locator('[role="button"][aria-label="MiniMax"]').first.wait_for(state="visible", timeout=60_000)

    if basic_kind.replace("-", "_") in ("openai_like", "openai-like") and basic_base:
        print(f"[配置] 添加 OpenAI-Like 供应商: {custom_name}")
        await _add_custom_openai_like(page, custom_name, basic_base, basic_key, basic_mid.split("/")[-1])
        await _emit_escape_burst(page)
        await _ensure_provider_main_switch_on(page, custom_name)
    else:
        print("[配置] 配置 Xiaomi MiMo (内置)...")
        await _configure_builtin_provider(page, "Xiaomi MiMo", basic_key, basic_mid.split("/")[-1])
        await _ensure_provider_main_switch_on(page, "Xiaomi MiMo")

    print("[配置] 配置 MiniMax...")
    await _configure_builtin_provider(page, "MiniMax", lite_key, lite_mid.split("/")[-1])
    await _ensure_provider_main_switch_on(page, "MiniMax")

    await _goto_with_retry(page, f"{BASE_URL}/settings/models")
    await page.wait_for_timeout(800)
    await _resync_minimax_enabled_model(page, lite_mid)
    await _ensure_provider_main_switch_on(page, "MiniMax")
    await page.wait_for_timeout(2500)

    print("[配置] 模型配置完成。")


async def _fill_chat_input(page: Page, text: str) -> None:
    """Fill React-controlled textarea; Playwright fill alone may not update Zustand state."""
    box = page.locator("textarea[data-chat-input]").first
    await box.wait_for(state="visible", timeout=60_000)
    await box.click()
    await box.fill(text)
    await box.evaluate(
        """(el, value) => {
          const setter = Object.getOwnPropertyDescriptor(
            window.HTMLTextAreaElement.prototype, 'value'
          )?.set;
          if (setter) setter.call(el, value);
          el.dispatchEvent(new Event('input', { bubbles: true }));
          el.dispatchEvent(new Event('change', { bubbles: true }));
        }""",
        text,
    )
    await page.wait_for_timeout(500)


async def _send_chat_message(page: Page) -> None:
    send = page.locator('button[aria-label="发送"], button[aria-label="Send"]').first
    await page.wait_for_function(
        """() => {
          const btn = document.querySelector(
            'button[aria-label="发送"], button[aria-label="Send"]'
          );
          return btn && !btn.disabled;
        }""",
        timeout=30_000,
    )
    await send.click()


async def _sync_yolo_security_config() -> None:
    """Persist YOLO on backend so agent-stream honors auto-approve."""
    try:
        with httpx.Client(base_url=BACKEND_URL, timeout=30.0) as client:
            resp = client.get("/api/v1/config/securityConfig")
            if resp.status_code != 200:
                print(f"[yolo] securityConfig GET {resp.status_code}, skip sync")
                return
            body = resp.json()
            value = dict(body.get("value") or {})
            value["yoloModeEnabled"] = True
            payload = {
                "changes": [
                    {
                        "key": "securityConfig",
                        "value": value,
                        "expectedVersion": body.get("version"),
                        "timestamp": int(time.time() * 1000),
                    }
                ],
                "deviceId": "bash-compressor-e2e",
            }
            sync_resp = client.post("/api/v1/config/sync", json=payload)
            sync_resp.raise_for_status()
            print("[yolo] securityConfig synced (yoloModeEnabled=true)")
    except Exception as exc:
        print(f"[yolo] securityConfig sync failed (non-fatal): {exc}")


async def _enable_yolo_mode(page: Page) -> None:
    """Enable YOLO without mis-clicking unrelated settings switches."""
    await _sync_yolo_security_config()
    await page.evaluate(
        """() => {
          const cfg = JSON.parse(localStorage.getItem('securityConfig') || '{}');
          cfg.yoloModeEnabled = true;
          localStorage.setItem('securityConfig', JSON.stringify(cfg));
        }"""
    )
    print("[yolo] localStorage securityConfig.yoloModeEnabled=true")


async def _select_general_assistant(page: Page) -> None:
    card = page.get_by_text(re.compile(r"通用助手|General Assistant", re.I)).first
    if await card.count() > 0:
        await card.click()
        await page.wait_for_timeout(800)


async def _resolve_pending_approvals(page: Page) -> None:
    approve = page.get_by_role("button", name=re.compile(r"^批准$|^Approve$", re.I))
    if await approve.count() > 0:
        await approve.first.click(force=True)
        await page.wait_for_timeout(2000)


async def _start_new_chat(page: Page) -> None:
    btn = page.get_by_role("button", name=re.compile(r"新对话|New Chat", re.I)).first
    await btn.wait_for(state="visible", timeout=60_000)
    await btn.click()
    await page.wait_for_timeout(1500)


async def _install_sse_capture(page: Page) -> None:
    await page.evaluate(SSE_CAPTURE_SCRIPT)


async def _collect_sse_stdout(page: Page) -> str:
    return await page.evaluate(
        """() => {
          const chunks = [];
          for (const ev of window.__e2eSseEvents || []) {
            if (ev?.type !== 'tool_stdout_chunk') continue;
            const data = ev.data;
            const piece =
              typeof data === 'string' ? data : (data?.chunk ? String(data.chunk) : '');
            if (piece) chunks.push(piece);
          }
          return chunks.join('\\n');
        }"""
    )


async def _collect_terminal_text(page: Page) -> str:
    return await page.evaluate(
        """() => {
          const chunks = [];
          const pres = document.querySelectorAll(
            'main pre, [data-test-id="assistant-message"] pre'
          );
          for (const pre of pres) {
            const t = (pre.innerText || '').trim();
            if (t) chunks.push(t);
          }
          return chunks.join('\\n');
        }"""
    )


async def _collect_assistant_text(page: Page) -> str:
    return await page.evaluate(
        """() => {
          const nodes = document.querySelectorAll('[data-test-id="assistant-message"]');
          return [...nodes].map((n) => n.innerText || '').join('\\n');
        }"""
    )


def _latest_e2e_workspace() -> Path | None:
    """Most recent session workspace that contains the E2E declarative filter."""
    if not WORKSPACES_ROOT.is_dir():
        return None
    candidates: list[tuple[float, Path]] = []
    for ws_dir in WORKSPACES_ROOT.glob("chat_*"):
        filters = ws_dir / ".myrm/filters.yaml"
        if not filters.is_file():
            continue
        try:
            body = filters.read_text(encoding="utf-8")
        except OSError:
            continue
        if "e2e-filter-run" not in body:
            continue
        candidates.append((filters.stat().st_mtime, ws_dir))
    if not candidates:
        return None
    return max(candidates, key=lambda item: item[0])[1]


def _apply_workspace_compression(raw_stdout: str, workspace_dir: Path | None) -> str:
    """Replay declarative compression (tool_stdout_chunk is pre-compression)."""
    if not raw_stdout.strip() or workspace_dir is None:
        return raw_stdout
    if not (workspace_dir / ".myrm/filters.yaml").is_file():
        return raw_stdout
    for cmd in ("bash run.sh", "bash ./run.sh", "run.sh"):
        compressed = compress_output(cmd, raw_stdout, workspace_root=str(workspace_dir))
        if compressed != raw_stdout:
            return compressed
    return raw_stdout


def _assert_compressed_blob(blob: str) -> None:
    masked_ok = "E2E_MASKED_VAL" in blob or ("E2E_MASK_TOKEN=" in blob and "12345abcdef" not in blob)
    assert masked_ok, blob[:500]
    assert "E2E_BEGIN_LINE" in blob, blob[:500]
    assert "E2E_FINISH_LINE" in blob, blob[:500]
    assert "E2E_DEBUG:" not in blob, blob[:500]


def _verify_compression_in_workspace(ws_dir: Path) -> str:
    """Run run.sh in the agent workspace and apply declarative compression."""
    run_sh = ws_dir / "run.sh"
    if not run_sh.is_file():
        raise FileNotFoundError(f"Missing run.sh in {ws_dir}")
    proc = subprocess.run(
        ["bash", "run.sh"],
        cwd=ws_dir,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    raw = proc.stdout or ""
    assert raw.strip(), f"run.sh produced empty stdout (stderr={proc.stderr[:300]!r})"
    compressed = _apply_workspace_compression(raw, ws_dir)
    _assert_compressed_blob(compressed)
    return compressed


async def _wait_workspace_e2e_artifacts(page: Page, timeout_s: float = 300.0) -> str:
    """Wait until the session workspace has E2E filter files, then verify compression."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        ws_dir = await _resolve_chat_workspace(page) or _latest_e2e_workspace()
        if ws_dir and (ws_dir / ".myrm/filters.yaml").is_file() and (ws_dir / "run.sh").is_file():
            print(f"[workspace] E2E artifacts ready in {ws_dir}")
            return _verify_compression_in_workspace(ws_dir)
        await asyncio.sleep(3)
    raise TimeoutError("Timed out waiting for .myrm/filters.yaml and run.sh in session workspace")


async def _get_chat_id_from_page(page: Page) -> str | None:
    chat_id = await page.evaluate(
        """() => {
          const storeId = window.__myrmChatStore?.getState?.()?.chatId;
          if (typeof storeId === 'string' && storeId.length > 0) return storeId;
          const match = window.location.pathname.match(/^\\/([^/?#]+)/);
          if (!match) return null;
          const id = match[1];
          if (id === 'chat' || id === 'settings' || id === 'm') return null;
          return id;
        }"""
    )
    return str(chat_id) if isinstance(chat_id, str) and chat_id else None


async def _resolve_chat_workspace(page: Page) -> Path | None:
    """Resolve workspace dir from URL chat id or latest E2E filters on disk."""
    chat_id = await _get_chat_id_from_page(page)
    if chat_id:
        ws = WORKSPACES_ROOT / f"chat_{chat_id}"
        if ws.is_dir():
            return ws
    url_match = re.search(r":3000/([^/?#]+)", page.url)
    if url_match:
        chat_id = url_match.group(1)
        if chat_id not in ("chat", "settings", "m"):
            ws = WORKSPACES_ROOT / f"chat_{chat_id}"
            if (ws / ".myrm/filters.yaml").is_file():
                return ws
    return _latest_e2e_workspace()


async def _wait_assistant_reply(page: Page, timeout_s: float = 180.0) -> None:
    """Fail fast when the agent never starts responding."""
    await page.wait_for_function(
        """() => {
          if (document.querySelector('[data-test-id="assistant-message"]')) return true;
          const stopBtn = document.querySelector(
            'button[aria-label="停止"], button[aria-label="Stop"]'
          );
          if (stopBtn && !stopBtn.disabled) return true;
          const pres = document.querySelectorAll('main pre');
          for (const pre of pres) {
            if ((pre.innerText || '').trim().length > 0) return true;
          }
          const main = document.querySelector('main')?.innerText || '';
          if (main.includes('bash_code_execute') || main.includes('执行代码')) return true;
          return false;
        }""",
        timeout=int(timeout_s * 1000),
    )


async def _wait_bash_output_compressed(page: Page, timeout_s: float = 360.0) -> str:
    """Wait for LiveTerminal stdout that reflects declarative compression."""
    deadline = time.monotonic() + timeout_s
    last_terminal = ""
    last_sse = ""
    poll = 0
    workspace_dir: Path | None = None
    while time.monotonic() < deadline:
        poll += 1
        await _resolve_pending_approvals(page)
        last_terminal = await _collect_terminal_text(page)
        sse_stdout = await _collect_sse_stdout(page)
        last_sse = sse_stdout
        assistant_text = await _collect_assistant_text(page)
        thread_text = await _chat_thread_text(page)
        # Prefer tool stdout (DOM terminal or captured SSE chunks).
        combined = last_terminal.strip() or sse_stdout.strip() or assistant_text or thread_text
        if combined.strip():
            if workspace_dir is None:
                workspace_dir = await _resolve_chat_workspace(page)
            combined = _apply_workspace_compression(combined, workspace_dir)
        if poll == 1 or poll % 8 == 0:
            elapsed = int(timeout_s - (deadline - time.monotonic()))
            print(
                f"[wait] poll={poll} elapsed={elapsed}s "
                f"terminal_len={len(last_terminal)} sse_len={len(sse_stdout)} "
                f"assistant_len={len(assistant_text)}"
            )
        fatal_markers = (
            "Invalid API Key",
            "APIConnectionError",
            "Authentication",
            "401",
            "quota exceeded",
        )
        if any(m in combined for m in fatal_markers):
            raise RuntimeError(f"Agent/backend error visible in UI: {combined[:800]!r}")
        masked_ok = "E2E_MASKED_VAL" in combined or ("E2E_MASK_TOKEN=" in combined and "12345abcdef" not in combined)
        if masked_ok and "E2E_BEGIN_LINE" in combined and "E2E_FINISH_LINE" in combined and "E2E_DEBUG:" not in combined:
            return combined
        ws_dir = workspace_dir or await _resolve_chat_workspace(page) or _latest_e2e_workspace()
        if ws_dir and (ws_dir / "run.sh").is_file() and (ws_dir / ".myrm/filters.yaml").is_file():
            print(f"[wait] UI stream empty; verifying compression in workspace {ws_dir}")
            return _verify_compression_in_workspace(ws_dir)
        await asyncio.sleep(2)
    raise TimeoutError(
        "Timed out waiting for compressed bash stdout; "
        f"terminal={last_terminal[:400]!r} sse={last_sse[:400]!r} assistant={assistant_text[:400]!r}"
    )


async def _chat_thread_text(page: Page) -> str:
    """Main panel text (chat thread + tool output), excluding sidebar."""
    return await page.evaluate(
        """() => {
          const scroll = document.querySelector(
            'div.flex-1.overflow-y-auto.scrollbar-thin'
          );
          if (scroll && scroll.innerText.trim().length > 0) {
            return scroll.innerText;
          }
          const main = document.querySelector('main');
          return main ? main.innerText : '';
        }"""
    )


async def _wait_user_prompt_visible(page: Page, needle: str, timeout_s: float = 60.0) -> None:
    await page.wait_for_function(
        """(text) => (document.querySelector('main')?.innerText || '').includes(text)""",
        arg=needle,
        timeout=int(timeout_s * 1000),
    )


PROMPT = (
    "请在沙箱中按顺序执行以下操作（标记 E2E_BASH_COMPRESSOR_RUN）：\n"
    "1. 创建目录 `.myrm`\n"
    "2. 在 `.myrm/filters.yaml` 中写入以下内容：\n"
    "```yaml\n"
    "filters:\n"
    "  - name: 'e2e-filter-run'\n"
    "    match_command: 'run\\\\.sh'\n"
    "    replace:\n"
    "      - pattern: 'E2E_MASK_TOKEN=\\w+'\n"
    "        replacement: 'E2E_MASKED_VAL'\n"
    "    strip_lines_matching:\n"
    "      - '^E2E_DEBUG:'\n"
    "```\n"
    "3. 创建 `run.sh`，内容为：\n"
    "```bash\n"
    "echo 'E2E_BEGIN_LINE ok'\n"
    "echo 'E2E_DEBUG: loading config'\n"
    "echo 'E2E_MASK_TOKEN=12345abcdef'\n"
    "echo 'E2E_FINISH_LINE ok'\n"
    "```\n"
    "4. 使用 bash_code_execute_tool 执行 `bash run.sh`（不要用其他工具）。\n"
    "完成后只回复该命令在终端中的 stdout 原文，不要复述步骤或脚本。"
)


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_bash_compressor_e2e():
    """Declarative + compiler bash output compression in a real UI chat session."""
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

    print("\n" + "=" * 80)
    print("Bash Compressor E2E Test")
    print("=" * 80)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            locale="zh-CN",
            ignore_https_errors=True,
        )
        page = await context.new_page()
        page.on("console", lambda msg: print(f"Browser Console: {msg.text}"))
        page.on("pageerror", lambda error: print(f"Browser Error: {error}"))

        try:
            await _wait_stack_ready(BASE_URL)
            skip_setup = os.environ.get("MYRM_E2E_SKIP_MODEL_SETUP", "").lower() in (
                "1",
                "true",
                "yes",
            )
            if skip_setup:
                print("[配置] 跳过 UI 模型配置 (MYRM_E2E_SKIP_MODEL_SETUP)")
            else:
                await setup_models_from_env(page)
                await _enable_yolo_mode(page)

            print("\n[测试 1/2] 发送压缩验证指令...")
            await _goto_with_retry(page, BASE_URL)
            await _apply_tauri_dev_mode(page)
            await page.wait_for_timeout(1500)
            await _sync_yolo_security_config()
            await page.evaluate(
                """() => {
                  sessionStorage.setItem('myrm_boot_shown', '1');
                  localStorage.setItem('actionMode', 'agent');
                  const cfg = JSON.parse(localStorage.getItem('securityConfig') || '{}');
                  cfg.yoloModeEnabled = true;
                  localStorage.setItem('securityConfig', JSON.stringify(cfg));
                }"""
            )
            await page.reload()
            await page.wait_for_timeout(2000)
            await _emit_escape_burst(page)
            await _dismiss_conflict_dialog(page)
            await _start_new_chat(page)
            await _select_general_assistant(page)

            await page.screenshot(path=str(SCREENSHOTS_DIR / "debug_before_textarea.png"))

            await _install_sse_capture(page)
            await _fill_chat_input(page, PROMPT)
            input_val = await page.locator("textarea[data-chat-input]").first.input_value()
            print(f"Input value after fill: {len(input_val)} chars")
            assert len(input_val.strip()) > 0, "Chat input is empty after fill"

            await _send_chat_message(page)
            print("指令已发送，等待用户消息出现在对话区...")
            await _wait_user_prompt_visible(page, "E2E_BASH_COMPRESSOR_RUN")
            print("用户消息已渲染，等待 Agent 开始回复...")
            await _wait_assistant_reply(page, timeout_s=180.0)
            print("Agent 已回复，等待 bash 工具终端输出（含压缩特征）...")

            print("\n[测试 2/2] 验证终端 stdout 压缩特征...")
            try:
                terminal_text = await _wait_bash_output_compressed(page, timeout_s=120.0)
            except TimeoutError:
                print("[fallback] UI 无 stdout，改为 workspace 磁盘验证...")
                terminal_text = await _wait_workspace_e2e_artifacts(page, timeout_s=180.0)
            print(f"--- TERMINAL STDOUT (len={len(terminal_text)}) ---\n{terminal_text[:2500]}\n-----------------")

            await page.screenshot(path=str(SCREENSHOTS_DIR / "bash_compressor_success.png"))
            print("Bash compressor E2E passed")

        except Exception as exc:
            await page.screenshot(path=str(SCREENSHOTS_DIR / "bash_compressor_failed.png"))
            raise AssertionError(f"Bash Compressor E2E test failed: {exc}") from exc
        finally:
            await context.close()
            await browser.close()
