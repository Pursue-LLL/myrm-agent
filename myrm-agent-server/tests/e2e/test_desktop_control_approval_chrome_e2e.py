"""Chrome E2E: desktop control approval via real WebUI SSE + Inspector banner.

Flow:
  enable computer_use → send agent message → desktop_interact triggers approval
  → click Allow once → tool resumes → assistant replies DONE.

Prerequisites:
  ./myrm ready --chrome  (macOS, Accessibility granted, provider ready)
"""

from __future__ import annotations

import asyncio
import os
import platform
import subprocess
import sys
from pathlib import Path

import pytest

_LIB = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from cdp_chat_support import chat_id_from_path, chat_user_message_count, get_e2e_api_url, wait_e2e_provider_ready  # noqa: E402
from chrome_mcp_client import ChromeMcpClient, McpPage  # noqa: E402
from mcp_chat_ui import McpChatSession  # noqa: E402

from tests.support.e2e_runtime_guard import E2EResourceLedger, heartbeat_e2e_lease

BASE_URL = os.getenv("E2E_UI_BASE", "http://127.0.0.1:3000").rstrip("/")
APPROVAL_WAIT_SEC = 240.0
TURN_WAIT_SEC = 300.0
MAX_SEND_ATTEMPTS = 3
E2E_PROMPT = (
    "TextEdit is open in the foreground with sample document text. "
    "Use desktop_snapshot_tool with scope=foreground and include_screenshot=false, "
    "then desktop_interact_tool to scroll_down on the first scrollable @dref you find. "
    "When both tool calls succeed, reply with exactly: DONE."
)


def _activate_textedit() -> None:
    if platform.system() != "Darwin":
        return
    subprocess.run(
        [
            "osascript",
            "-e",
            'tell application "TextEdit" to activate',
            "-e",
            'tell application "TextEdit"',
            "-e",
            "if (count of documents) is 0 then make new document",
            "-e",
            'set text of document 1 to "E2E desktop control scroll target line 1" & return & "E2E desktop control scroll target line 2" & return & "E2E desktop control scroll target line 3"',
            "-e",
            "end tell",
            "-e",
            'tell application "System Events" to tell process "TextEdit" to set frontmost to true',
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )


async def _resolve_chat_id(chat: McpChatSession, state: dict[str, object]) -> str | None:
    chat_id = chat_id_from_path(str(state.get("url") or ""))
    if chat_id:
        return chat_id
    explicit = str(state.get("chatId") or "").strip()
    if explicit:
        return explicit
    path = await chat.evaluate("(() => location.pathname)()", await_promise=False)
    return chat_id_from_path(str(path) if path else "")


async def _wait_stream_done_with_marker(
    chat: McpChatSession,
    *,
    chat_id_hint: str | None,
    marker: str,
    timeout_sec: float,
) -> dict[str, object]:
    deadline = asyncio.get_event_loop().time() + timeout_sec
    last: dict[str, object] = {}
    while asyncio.get_event_loop().time() < deadline:
        heartbeat_e2e_lease()
        probe = await chat.evaluate(
            f"""(() => {{
              const snap = window.__MYRM_E2E_CHAT__?.turnSnapshot?.() ?? {{}};
              const sample = String(snap.lastAssistantSample ?? '');
              const marker = {marker!r};
              const re = new RegExp(`\\\\b${{marker}}\\\\b`, 'i');
              return {{
                chatId: snap.chatId ?? null,
                userCount: snap.userCount ?? 0,
                isStreaming: Boolean(snap.isStreaming),
                matched: re.test(sample),
                lastAssistantSample: sample,
              }};
            }})()""",
            await_promise=False,
        )
        if isinstance(probe, dict):
            last = probe
            chat_id = str(probe.get("chatId") or chat_id_hint or "").strip()
            if (
                chat_id
                and int(probe.get("userCount") or 0) >= 1
                and not probe.get("isStreaming")
                and probe.get("matched")
            ):
                return {**probe, "chatId": chat_id}
        await asyncio.sleep(2.0)
    return {**last, "ok": False, "err": "turn-timeout"}


async def _run_approval_attempt(chat: McpChatSession) -> str:
    await chat.click_new_chat()
    await chat.ensure_chat_surface(BASE_URL)
    _activate_textedit()
    await asyncio.sleep(3.0)

    tools_setup = await chat.enable_computer_use()
    assert tools_setup.get("ok") is True, f"computer_use bridge failed: {tools_setup}"
    assert "computer_use" in (tools_setup.get("tools") or []), tools_setup

    heartbeat_e2e_lease()
    await chat.send_message(E2E_PROMPT, E2E_PROMPT)
    heartbeat_e2e_lease()

    approval = await chat.wait_desktop_approval_pending(timeout_sec=APPROVAL_WAIT_SEC)
    if approval.get("err") == "model-completed-without-desktop-tools":
        raise AssertionError(f"Model finished without desktop tools: {approval}")
    assert approval.get("pending") is True, f"Expected desktop approval banner: {approval}"
    assert approval.get("allowVisible") is True, f"Allow-once button not visible: {approval}"

    click = await chat.click_desktop_allow_once()
    assert click.get("ok") is True, f"Allow-once click failed: {click}"

    chat_id_hint = str(
        (await chat.evaluate(
            "(() => window.__MYRM_E2E_CHAT__?.turnSnapshot?.()?.chatId ?? null)()",
            await_promise=False,
        ))
        or ""
    ).strip() or None

    after_turn = await _wait_stream_done_with_marker(
        chat,
        chat_id_hint=chat_id_hint,
        marker="DONE",
        timeout_sec=TURN_WAIT_SEC,
    )
    if str(after_turn.get("path", "")).startswith("/settings"):
        pytest.fail(f"Send redirected to settings: {after_turn}")
    assert after_turn.get("matched") is True, (
        f"Turn did not complete with DONE after approval: {after_turn}"
    )

    chat_id = await _resolve_chat_id(chat, after_turn)
    assert chat_id, f"Expected chat id after approval turn: {after_turn}"
    assert chat_user_message_count(chat_id) >= 1, after_turn
    return chat_id


@pytest.mark.chrome_e2e(lane="LIVE_AGENT")
@pytest.mark.integration
@pytest.mark.timeout(1800)
@pytest.mark.skipif(platform.system() != "Darwin", reason="macOS computer_use only")
@pytest.mark.asyncio
async def test_chrome_ui_desktop_control_approval_allow_once(
    e2e_resource_ledger: E2EResourceLedger,
) -> None:
    if not wait_e2e_provider_ready():
        pytest.fail(
            "Provider config not ready for live E2E — run via ./myrm test -m chrome_e2e "
            "after ./myrm ready --chrome"
        )

    _activate_textedit()

    async def run_flow(chat: McpChatSession) -> str:
        await chat.bootstrap(BASE_URL, navigate=False, timeout_sec=120.0)

        last_error: dict[str, object] | None = None
        for attempt in range(1, MAX_SEND_ATTEMPTS + 1):
            heartbeat_e2e_lease()
            try:
                chat_id = await _run_approval_attempt(chat)
                e2e_resource_ledger.register("chat", chat_id)
                return chat_id
            except AssertionError as exc:
                last_error = {"attempt": attempt, "error": str(exc)}
                if attempt >= MAX_SEND_ATTEMPTS:
                    break
                await chat.evaluate(
                    "(() => { window.__MYRM_E2E_CHAT__?.resetChat?.(); return { ok: true }; })()",
                    await_promise=False,
                )
                await asyncio.sleep(2.0)

        pytest.fail(
            f"Desktop approval Chrome E2E failed after {MAX_SEND_ATTEMPTS} attempts "
            f"(api={get_e2e_api_url()}): {last_error}"
        )

    client = ChromeMcpClient(request_timeout_sec=180.0)
    await asyncio.to_thread(client.start)
    try:
        page: McpPage | None = None
        try:
            page = await asyncio.to_thread(client.new_page, BASE_URL, timeout_ms=120_000)
        except TimeoutError:
            await asyncio.sleep(2.0)
            page = await asyncio.to_thread(client.new_page, BASE_URL, timeout_ms=120_000)
        chat = McpChatSession(client, page)
        await run_flow(chat)
    finally:
        client.close()
