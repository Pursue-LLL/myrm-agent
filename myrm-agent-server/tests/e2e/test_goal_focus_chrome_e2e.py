"""Chrome E2E: Goal mode via real WebUI (CDP, not Playwright).

Prerequisites:
  ./myrm ready --chrome
  WebUI default model configured (E2E Chrome profile DB)
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import urllib.request
from contextlib import AsyncExitStack
from pathlib import Path
from urllib.parse import urlparse

import pytest

_LIB = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "lib"
_PREFLIGHT = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "chrome-e2e-preflight.sh"
_MYRM_AGENT_ROOT = Path(__file__).resolve().parents[3]
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from cdp_chat_ui import (  # noqa: E402
    CdpChatSession,
    chat_id_from_path,
    close_owned_page,
    create_owned_page,
    warmup_frontend,
)

BASE_URL = "http://127.0.0.1:3000"
API_URL = "http://127.0.0.1:8080"
E2E_PROMPT = "只回复 GOAL_OK"


def _provider_ready() -> bool:
    try:
        resp = urllib.request.urlopen(  # noqa: S310 - fixed loopback E2E endpoint
            f"{API_URL}/api/v1/config/readiness",
            timeout=5,
        )
        payload = json.loads(resp.read())
    except Exception:
        return False
    provider = payload.get("provider")
    return isinstance(provider, dict) and bool(provider.get("is_ready"))


def _fetch_goal_status(chat_id: str) -> dict[str, object] | None:
    try:
        resp = urllib.request.urlopen(  # noqa: S310
            f"{API_URL}/api/v1/goals/{chat_id}/status",
            timeout=15,
        )
        payload = json.loads(resp.read())
    except Exception:
        return None
    goal = payload.get("goal")
    return goal if isinstance(goal, dict) else None


@pytest.fixture(scope="module")
def _chrome_client_hot() -> None:
    try:
        resp = urllib.request.urlopen("http://127.0.0.1:9333/json/version", timeout=3)
        json.loads(resp.read())
    except Exception as exc:
        pytest.skip(f"Chrome E2E not ready — run ./myrm ready --chrome first: {exc}")


@pytest.fixture(scope="module")
def _frontend_warm() -> None:
    try:
        warmup_frontend(BASE_URL, timeout_sec=45)
    except TimeoutError:
        if not _PREFLIGHT.is_file():
            raise
        subprocess.run(
            ["bash", str(_PREFLIGHT)],
            cwd=str(_MYRM_AGENT_ROOT),
            check=True,
            timeout=300,
        )
        warmup_frontend(BASE_URL, timeout_sec=120)


@pytest.mark.e2e
@pytest.mark.integration
@pytest.mark.timeout(600)
@pytest.mark.asyncio
async def test_chrome_ui_goal_mode_stream(
    _chrome_client_hot: None,
    _frontend_warm: None,
) -> None:
    import websockets

    if not _provider_ready():
        pytest.skip(
            "Provider config not ready — configure model at /settings/models "
            "(API /api/v1/config/readiness provider.is_ready must be true)"
        )

    async def _run_goal_turn() -> str:
        owned_page = create_owned_page(BASE_URL)
        async with AsyncExitStack() as stack:
            stack.callback(close_owned_page, owned_page)
            ws = await stack.enter_async_context(
                websockets.connect(owned_page.websocket_url, max_size=10**7, open_timeout=10)
            )
            chat = CdpChatSession(ws)
            await chat.bootstrap(BASE_URL)
            await chat.cdp("Runtime.enable")
            await chat.cdp("Page.enable")
            await chat.dismiss_modals()

            await chat.evaluate(
                """(() => {
                  const newBtn = Array.from(document.querySelectorAll('aside button')).find((b) => {
                    const text = (b.textContent || '').trim();
                    return text.includes('新对话') || text.includes('New chat');
                  });
                  if (newBtn) newBtn.click();
                  return { ok: true };
                })()""",
                await_promise=False,
            )
            await asyncio.sleep(1)

            goal_setup = await chat.enable_goal_mode(budget_tokens=50_000)
            assert goal_setup.get("ok") is True, f"Goal mode bridge failed: {goal_setup}"

            await chat.send_message(E2E_PROMPT, E2E_PROMPT)
            after_turn = await chat.wait_turn_done(E2E_PROMPT, timeout_sec=180)
            if str(after_turn.get("path", "")).startswith("/settings"):
                pytest.fail(f"Send redirected to settings: {after_turn}")

            chat_id = chat_id_from_path(str(after_turn.get("url") or ""))
            if not chat_id:
                path = await chat.evaluate("(() => location.pathname)()", await_promise=False)
                chat_id = chat_id_from_path(str(path) if path else "")
            assert chat_id, f"Expected chat id after goal turn: {after_turn}"
            assert int(after_turn.get("userMsgs") or 0) >= 1, f"Expected user message: {after_turn}"
            return chat_id

    chat_id = ""
    for attempt in range(2):
        try:
            chat_id = await _run_goal_turn()
            break
        except (TimeoutError, OSError, RuntimeError, websockets.exceptions.ConnectionClosedError):
            if attempt == 1:
                raise
            await asyncio.sleep(2)
            continue

    goal = _fetch_goal_status(chat_id)
    assert goal is not None, f"Goal status missing for chat {chat_id}"
    assert goal.get("objective"), f"Goal objective empty: {goal}"
    assert goal.get("status") in {"active", "budget_limited", "complete", "paused"}, (
        f"Unexpected goal status: {goal.get('status')}"
    )
