"""Chrome E2E: POOLED execution cache via real WebUI (CDP, not Playwright).

Prerequisites:
  ./myrm ready --chrome
  WebUI default model configured (E2E Chrome profile DB)
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
import urllib.request
from pathlib import Path

import pytest

_LIB = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from cdp_chat_ui import (  # noqa: E402
    CdpChatSession,
    count_execution_cache_in_log,
    create_fresh_page_ws,
    snapshot_backend_log_offset,
)

BASE_URL = "http://127.0.0.1:3000"
API_URL = "http://127.0.0.1:8080"
E2E_PROMPT = "只回复 OK"
CHAT_ID_RE = re.compile(
    r"^/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|c-[a-z0-9\-]+)$",
    re.IGNORECASE,
)


def _provider_ready() -> bool:
    try:
        resp = urllib.request.urlopen(f"{API_URL}/api/v1/config/readiness", timeout=5)
        payload = json.loads(resp.read())
    except Exception:
        return False
    provider = payload.get("provider")
    return isinstance(provider, dict) and bool(provider.get("is_ready"))


@pytest.fixture(scope="module")
def _chrome_client_hot() -> None:
    try:
        resp = urllib.request.urlopen("http://127.0.0.1:9333/json/version", timeout=3)
        json.loads(resp.read())
    except Exception as exc:
        pytest.skip(f"Chrome E2E not ready — run ./myrm ready --chrome first: {exc}")


def _extract_chat_id(url: str) -> str | None:
    from urllib.parse import urlparse

    path = urlparse(url).path
    match = CHAT_ID_RE.match(path)
    return match.group(1) if match else None


@pytest.mark.e2e
@pytest.mark.integration
@pytest.mark.timeout(420)
@pytest.mark.asyncio
async def test_chrome_ui_same_chat_two_ok_messages(_chrome_client_hot: None) -> None:
    """Real WebUI: two agent turns in one chat must both return OK and reuse cache."""
    import websockets

    if not _provider_ready():
        pytest.skip(
            "Provider config not ready — configure model at /settings/models "
            "(API /api/v1/config/readiness provider.is_ready must be true)"
        )

    log_offset = snapshot_backend_log_offset()

    async def _run_turns() -> None:
        ws_url = create_fresh_page_ws(BASE_URL)
        async with websockets.connect(ws_url, max_size=10**7, open_timeout=10) as ws:
            chat = CdpChatSession(ws)
            await chat.bootstrap(BASE_URL)
            await chat.cdp("Runtime.enable")
            await chat.cdp("Page.enable")
            await chat.dismiss_modals()

            await chat.send_message(E2E_PROMPT, E2E_PROMPT)
            after_first = await chat.wait_turn_done(E2E_PROMPT)
            if str(after_first.get("path", "")).startswith("/settings"):
                pytest.fail(f"Send redirected to settings: {after_first}")

            chat_id = _extract_chat_id(str(after_first.get("url") or ""))
            if not chat_id:
                href = await chat.evaluate(
                    """(() => {
                      const links = Array.from(document.querySelectorAll('aside a[href]'))
                        .map((a) => a.href)
                        .filter((h) => /:3000\\//.test(h) && !h.endsWith('/') && !h.includes('/settings'));
                      return links[0] || location.href;
                    })()""",
                    await_promise=False,
                )
                chat_id = _extract_chat_id(str(href) if href else "")
            assert chat_id, f"Expected chat id after first turn: {after_first}"

            first_user_msgs = int(after_first.get("userMsgs") or 0)

            await chat.wait_input_empty()
            await chat.send_message(E2E_PROMPT, E2E_PROMPT)
            after_second = await chat.wait_turn_done(E2E_PROMPT)
            chat_id_second = _extract_chat_id(str(after_second.get("url") or ""))
            if not chat_id_second:
                href = await chat.evaluate(
                    """(() => {
                      const links = Array.from(document.querySelectorAll('aside a[href]'))
                        .map((a) => a.href)
                        .filter((h) => /:3000\\//.test(h) && !h.endsWith('/') && !h.includes('/settings'));
                      return links[0] || location.href;
                    })()""",
                    await_promise=False,
                )
                chat_id_second = _extract_chat_id(str(href) if href else "")
            assert chat_id_second == chat_id, (
                f"Second turn changed chat id: {chat_id} -> {chat_id_second}"
            )
            assert int(after_second.get("userMsgs") or 0) >= first_user_msgs + 1, (
                f"Expected another user message: {after_first} -> {after_second}"
            )

    for attempt in range(2):
        try:
            await _run_turns()
            break
        except (TimeoutError, OSError, RuntimeError) as exc:
            if attempt == 1:
                raise
            await asyncio.sleep(2)
            continue

    created, reused = count_execution_cache_in_log(since_offset=log_offset)
    assert created == 1, f"expected execution_cache_created×1 in backend log (got {created})"
    assert reused >= 1, f"expected execution_cache_reuse≥1 in backend log (got {reused})"
