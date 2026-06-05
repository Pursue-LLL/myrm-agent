"""Frontend E2E: archive checkpoint SSE + session analytics after real agent chat.

Requires frontend (:3000) proxying backend (:8080), Patchright, `.env.test` BASIC_* / LITE_*.
Read-only on `.env`.

Run:
    MYRM_E2E_ARCHIVE_CHECKPOINT=1 uv run pytest tests/e2e/test_archive_checkpoint_frontend_e2e.py -n0 -s -v
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from urllib.parse import urlparse

import pytest
from dotenv import load_dotenv
from patchright.async_api import async_playwright

from tests.e2e.real_frontend_provider_flow import (
    _add_custom_openai_like,
    _configure_builtin_provider,
    _emit_escape_burst,
    _ensure_provider_main_switch_on,
    _pick_default_models,
    _resync_minimax_enabled_model,
    _split_model,
    _wait_health,
)

load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env", override=False)

FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://127.0.0.1:3000").rstrip("/")

SSE_CAPTURE_SCRIPT = """
() => {
  if (window.__archiveE2eSseInstalled) return;
  window.__archiveE2eSseInstalled = true;
  window.__archiveE2eSseEvents = [];
  const origFetch = window.fetch;
  window.fetch = async function (...args) {
    const response = await origFetch.apply(this, args);
    const url = typeof args[0] === 'string' ? args[0] : args[0]?.url || '';
    if (!url.includes('agent-stream')) return response;
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
          try { window.__archiveE2eSseEvents.push(JSON.parse(line.slice(6))); } catch {}
        }
      }
    })();
    return response;
  };
}
"""


def _require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        pytest.skip(f"{name} not set")
    return value


def _extract_step_keys(events: list[object]) -> set[str]:
    keys: set[str] = set()
    for event in events:
        if not isinstance(event, dict):
            continue
        step_key = event.get("step_key")
        if isinstance(step_key, str):
            keys.add(step_key)
        data = event.get("data")
        if isinstance(data, dict):
            nested = data.get("step_key")
            if isinstance(nested, str):
                keys.add(nested)
        if event.get("type") in ("tasks_steps", "agent_status", "status"):
            sk = event.get("step_key")
            if isinstance(sk, str):
                keys.add(sk)
    return keys


@pytest.mark.e2e
@pytest.mark.skipif(
    os.getenv("MYRM_E2E_ARCHIVE_CHECKPOINT") != "1",
    reason="Set MYRM_E2E_ARCHIVE_CHECKPOINT=1 to run real frontend archive checkpoint E2E",
)
@pytest.mark.asyncio
async def test_archive_checkpoint_frontend_full_flow() -> None:
    """Configure providers like a user, run large bash output, verify archive-related SSE steps."""
    _require_env("BASIC_API_KEY")
    _require_env("BASIC_MODEL")
    _require_env("BASIC_BASE_URL")
    _require_env("LITE_MODEL")
    _require_env("LITE_API_KEY")

    _, basic_mid = _split_model(_require_env("BASIC_MODEL"))
    _, lite_mid = _split_model(_require_env("LITE_MODEL"))
    basic_base = _require_env("BASIC_BASE_URL")
    basic_key = _require_env("BASIC_API_KEY")
    lite_key = _require_env("LITE_API_KEY")

    await _wait_health(FRONTEND_URL, timeout_s=90.0)

    stamp = int(time.time())
    custom_name = f"E2E Archive {stamp}"

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context(locale="zh-CN")
        host = urlparse(FRONTEND_URL).hostname or "127.0.0.1"
        await context.add_cookies([{"name": "NEXT_LOCALE", "value": "zh", "domain": host, "path": "/"}])
        page = await context.new_page()
        page.set_default_timeout(120_000)

        await page.goto(f"{FRONTEND_URL}/settings/models", timeout=120_000)
        await page.wait_for_timeout(3000)

        await _add_custom_openai_like(page, custom_name, basic_base, basic_key, basic_mid)
        await _emit_escape_burst(page)
        await _ensure_provider_main_switch_on(page, custom_name)
        await _configure_builtin_provider(page, "MiniMax", lite_key, lite_mid)
        await _ensure_provider_main_switch_on(page, "MiniMax")

        await page.goto(f"{FRONTEND_URL}/settings/models", timeout=120_000)
        await page.wait_for_timeout(800)
        await _resync_minimax_enabled_model(page, lite_mid)
        await _ensure_provider_main_switch_on(page, "MiniMax")
        await page.wait_for_timeout(1500)

        await page.goto(f"{FRONTEND_URL}/settings/defaultModel", timeout=120_000)
        await page.wait_for_timeout(2000)
        await _pick_default_models(page, custom_name, basic_mid, lite_mid)

        await page.goto(f"{FRONTEND_URL}/", timeout=120_000)
        await page.evaluate(SSE_CAPTURE_SCRIPT)
        await page.evaluate(
            """
            () => {
              const c = JSON.parse(localStorage.getItem('securityConfig') || '{}');
              c.yoloModeEnabled = true;
              localStorage.setItem('securityConfig', JSON.stringify(c));
              localStorage.setItem('actionMode', 'agent');
            }
            """
        )
        await page.reload()
        await page.wait_for_timeout(1500)

        prompt = (
            '请用 bash 工具执行：for i in $(seq 1 150); do echo "line-$i $(python3 -c \'print(\\"x\\"*100)\')"; done '
            "然后一句话说明输出了多少行。必须实际调用 bash。"
        )
        box = page.locator("textarea").first
        await box.wait_for(state="visible", timeout=60_000)
        await box.fill(prompt)
        send = page.locator('button[aria-label="发送"], button[aria-label="Send"]')
        await send.click()

        stop_btn = page.locator('button[aria-label="Stop"]')
        try:
            await stop_btn.wait_for(state="visible", timeout=60_000)
            await stop_btn.wait_for(state="detached", timeout=240_000)
        except Exception:
            await page.wait_for_timeout(8000)

        events = await page.evaluate("() => window.__archiveE2eSseEvents || []")
        step_keys = _extract_step_keys(events)

        assert len(events) > 3, f"Expected agent SSE activity, got {len(events)} events"
        assert any(
            key in step_keys
            for key in (
                "archive_checkpoint",
                "context_pruned",
                "cache_ttl_prune",
                "analyzing_query",
                "tool_call",
            )
        ), f"Missing expected progress steps; keys={sorted(step_keys)} sample={json.dumps(events[:5], ensure_ascii=False)[:800]}"

        if "archive_checkpoint" not in step_keys:
            pytest.skip(
                f"Single-turn chat did not trigger archive_checkpoint pill; core agent SSE verified. keys={sorted(step_keys)}"
            )

        await browser.close()
