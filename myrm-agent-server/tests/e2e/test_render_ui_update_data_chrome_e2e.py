"""Chrome LIVE_AGENT E2E: update_ui_data_tool refreshes inline A2UI in real Web Chat."""

from __future__ import annotations

import asyncio
import os
import sys
import time
import urllib.error
from pathlib import Path

import pytest

_LIB = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from cdp_chat_support import (
    chat_user_message_count,
    fetch_chat_messages,
    get_e2e_api_url,
    wait_e2e_backend_ready,
    wait_e2e_provider_ready,
)  # noqa: E402
from cdp_chat_ui import chat_id_from_path  # noqa: E402
from chrome_mcp_client import ChromeMcpClient, McpPage  # noqa: E402
from mcp_chat_ui import McpChatSession  # noqa: E402

from tests.support.e2e_runtime_guard import E2EResourceLedger, heartbeat_e2e_lease

BASE_URL = os.getenv("E2E_UI_BASE", "http://127.0.0.1:3000").rstrip("/")

E2E_PROMPT_RENDER = (
    "Call render_ui_tool exactly once. Required arguments: "
    'title="E2E_UPDATE_MARKER_ALPHA"; '
    'components=[{"id":"s1","type":"text","props":{"variant":"body"},'
    '"bindings":{"text":"$.status"}}]; '
    'root_ids=["s1"]; data={"status":"E2E_UPDATE_INITIAL"}. '
    "Every component MUST include a type field. "
    "Do not use any other tools. After render_ui_tool succeeds, reply DONE."
)

E2E_PROMPT_UPDATE = (
    "Call update_ui_data_tool exactly once on the interactive UI you just rendered in this chat. "
    'updates={"status":"E2E_UPDATE_FINAL"}. '
    "Use the correct surface_id from the existing UI artifact. "
    "Do NOT call render_ui_tool. After update_ui_data_tool succeeds, reply DONE."
)

_ENABLE_RENDER_UI_JS = """(() => {
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge?.setCurrentBuiltinTools) {
    return { ok: false, err: 'no-bridge' };
  }
  bridge.setCurrentBuiltinTools(['render_ui']);
  const tools = bridge.getCurrentBuiltinTools?.() ?? [];
  return { ok: tools.includes('render_ui'), tools };
})()"""

_ENABLE_UPDATE_UI_JS = """(() => {
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge?.setCurrentBuiltinTools) {
    return { ok: false, err: 'no-bridge' };
  }
  bridge.setCurrentBuiltinTools(['render_ui']);
  const tools = bridge.getCurrentBuiltinTools?.() ?? [];
  return { ok: tools.includes('render_ui'), tools };
})()"""

_INITIAL_READY_JS = """(() => {
  const main = document.querySelector('main');
  const text = main?.innerText || '';
  const hasTitle = /E2E_UPDATE_MARKER_ALPHA/.test(text);
  const hasInitial = /E2E_UPDATE_INITIAL/.test(text);
  const hasFinal = /E2E_UPDATE_FINAL/.test(text);
  const sending = !!main?.querySelector('button[aria-label="Stop"]');
  return {
    ready: hasTitle && hasInitial && !hasFinal && !sending,
    hasTitle,
    hasInitial,
    hasFinal,
    sending,
    onChat: /^\\/c-/.test(location.pathname),
    path: location.pathname,
    sample: text.slice(0, 900),
  };
})()"""

_UPDATE_DATA_READY_JS = """(() => {
  const main = document.querySelector('main');
  const text = main?.innerText || '';
  const hasTitle = /E2E_UPDATE_MARKER_ALPHA/.test(text);
  const hasInitial = /E2E_UPDATE_INITIAL/.test(text);
  const hasFinal = /E2E_UPDATE_FINAL/.test(text);
  const sending = !!main?.querySelector('button[aria-label="Stop"]');
  return {
    ready: hasTitle && hasFinal && !hasInitial && !sending,
    hasTitle,
    hasInitial,
    hasFinal,
    sending,
    onChat: /^\\/c-/.test(location.pathname),
    path: location.pathname,
    sample: text.slice(0, 900),
  };
})()"""


def _host_ui_artifact_status_label(chat_id: str, api_base: str) -> str | None:
    messages = fetch_chat_messages(chat_id, api_url=api_base)
    for message in reversed(messages):
        if not isinstance(message, dict) or message.get("role") != "assistant":
            continue
        metadata = message.get("metadata")
        if not isinstance(metadata, dict):
            continue
        artifacts = metadata.get("uiArtifacts")
        if not isinstance(artifacts, list):
            continue
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                continue
            data = artifact.get("data")
            if not isinstance(data, dict):
                continue
            status = data.get("status")
            if isinstance(status, str) and status.startswith("E2E_UPDATE_"):
                return status
    return None


async def _wait_db_ui_status(
    chat_id: str,
    api_base: str,
    expected: str,
    *,
    timeout_sec: float,
) -> str:
    deadline = time.monotonic() + timeout_sec
    last: str | None = None
    while time.monotonic() < deadline:
        heartbeat_e2e_lease()
        try:
            last = _host_ui_artifact_status_label(chat_id, api_base)
            if last == expected:
                return last
        except (OSError, TimeoutError, urllib.error.URLError):
            wait_e2e_backend_ready(timeout_sec=15.0, api_url=api_base)
        await asyncio.sleep(1.0)
    raise AssertionError(
        f"DB uiArtifacts status did not reach {expected!r} within {timeout_sec}s (last={last!r})"
    )


@pytest.mark.chrome_e2e(lane="LIVE_AGENT", private_backend=False)
@pytest.mark.integration
@pytest.mark.timeout(900)
@pytest.mark.asyncio
async def test_render_ui_update_data_refreshes_inline_binding_in_real_chat(
    e2e_resource_ledger: E2EResourceLedger,
) -> None:
    if not wait_e2e_provider_ready():
        pytest.fail(
            "Provider config not ready for live update_ui_data Chrome E2E — run via "
            "./myrm test -m chrome_e2e after ./myrm ready --chrome",
        )

    api_base = get_e2e_api_url()

    async def _wait_js(
        chat: McpChatSession,
        chat_id: str,
        js: str,
        *,
        timeout_sec: float,
        error_label: str,
    ) -> dict[str, object]:
        deadline = time.monotonic() + timeout_sec
        last: dict[str, object] = {}
        while time.monotonic() < deadline:
            heartbeat_e2e_lease()
            raw = await chat.evaluate(js, await_promise=False, recv_timeout=30.0)
            last = raw if isinstance(raw, dict) else {"value": raw}
            if last.get("ready") is True:
                return last
            if last.get("onChat") is not True and chat_id:
                await chat.navigate_to_chat(chat_id, BASE_URL, timeout_sec=60.0)
            await asyncio.sleep(1.0)
        raise AssertionError(f"{error_label}: {last}")

    async def _focus_chat(chat: McpChatSession, chat_id: str) -> None:
        expected_path = f"/{chat_id.strip()}"
        await chat.dismiss_modals()
        for _ in range(3):
            await chat.navigate_to_chat(chat_id, BASE_URL, timeout_sec=60.0)
            probe = await chat.evaluate(
                """(() => ({
                  path: location.pathname,
                  hasInput: !!document.querySelector('[data-chat-input]'),
                }))()""",
                await_promise=False,
                recv_timeout=15.0,
            )
            if (
                isinstance(probe, dict)
                and str(probe.get("path") or "") == expected_path
                and probe.get("hasInput") is True
            ):
                return
            await asyncio.sleep(1.0)
        raise AssertionError(f"Could not focus chat {chat_id}: {probe}")

    async def _run_flow(chat: McpChatSession) -> str:
        await chat.dismiss_modals()
        await chat.click_new_chat()
        await chat.ensure_chat_surface(BASE_URL)

        enabled = await chat.evaluate(_ENABLE_RENDER_UI_JS, await_promise=False, recv_timeout=15.0)
        assert isinstance(enabled, dict)
        assert enabled.get("ok") is True, f"Failed to enable render_ui in chat session: {enabled}"

        render_send = await chat.send_message(E2E_PROMPT_RENDER, E2E_PROMPT_RENDER)
        heartbeat_e2e_lease()
        chat_id_hint = str(
            render_send.get("started", {}).get("chatId")
            or render_send.get("submit", {}).get("chatId")
            or ""
        ).strip()
        if not chat_id_hint:
            chat_id_hint = str((await chat.bridge_chat_id()) or "").strip() or None

        started = await chat.wait_stream_started(E2E_PROMPT_RENDER, timeout_sec=120.0, chat_id_hint=chat_id_hint)
        chat_id = chat_id_hint or str(started.get("chatId") or "").strip() or None
        if not chat_id:
            after_start = await chat.main_state(E2E_PROMPT_RENDER, recv_timeout=30.0)
            chat_id = chat_id_from_path(str(after_start.get("path") or "")) or str(
                after_start.get("bridgeChatId") or ""
            ).strip() or None
        assert chat_id, f"Expected chat id after stream start: started={started}; send={render_send}"
        await chat.navigate_to_chat(chat_id, BASE_URL, timeout_sec=90.0)
        await chat.ensure_chat_surface(BASE_URL)

        await _wait_js(
            chat,
            chat_id,
            _INITIAL_READY_JS,
            timeout_sec=300.0,
            error_label="render_ui binding card did not appear",
        )

        turn1_db_status = await _wait_db_ui_status(
            chat_id,
            api_base,
            "E2E_UPDATE_INITIAL",
            timeout_sec=60.0,
        )
        assert turn1_db_status == "E2E_UPDATE_INITIAL"

        async def _wait_not_streaming(*, timeout_sec: float) -> None:
            deadline = time.monotonic() + timeout_sec
            last: dict[str, object] = {}
            while time.monotonic() < deadline:
                heartbeat_e2e_lease()
                probe = await chat.evaluate(
                    """(() => window.__MYRM_E2E_CHAT__?.turnSnapshot?.() ?? { err: 'no-bridge' })()""",
                    await_promise=False,
                    recv_timeout=15.0,
                )
                if isinstance(probe, dict):
                    last = probe
                    if probe.get("isStreaming") is False:
                        return
                await asyncio.sleep(1.0)
            raise TimeoutError(f"Chat still streaming before turn2: {last}")

        await _wait_not_streaming(timeout_sec=120.0)
        await chat.wait_input_empty(chat_id_hint=chat_id)

        await chat.evaluate(_ENABLE_UPDATE_UI_JS, await_promise=False, recv_timeout=15.0)

        await chat.send_message(
            E2E_PROMPT_UPDATE,
            E2E_PROMPT_UPDATE,
            chat_id_hint=chat_id,
            base_url=BASE_URL,
        )
        heartbeat_e2e_lease()
        await chat.wait_stream_started(
            E2E_PROMPT_UPDATE,
            timeout_sec=120.0,
            chat_id_hint=chat_id,
            min_user_msgs=2,
        )

        async def _wait_api_user_messages(min_count: int, *, timeout_sec: float) -> None:
            deadline = time.monotonic() + timeout_sec
            last = 0
            while time.monotonic() < deadline:
                heartbeat_e2e_lease()
                try:
                    last = chat_user_message_count(chat_id, api_url=api_base)
                    if last >= min_count:
                        return
                except (OSError, TimeoutError, urllib.error.URLError):
                    wait_e2e_backend_ready(timeout_sec=15.0, api_url=api_base)
                await asyncio.sleep(1.0)
            raise AssertionError(
                f"Backend did not persist turn2 user message within {timeout_sec}s (last={last})"
            )

        await _wait_api_user_messages(2, timeout_sec=120.0)
        ui_state = await _wait_js(
            chat,
            chat_id,
            _UPDATE_DATA_READY_JS,
            timeout_sec=300.0,
            error_label="update_ui_data did not refresh inline binding UI",
        )

        await _wait_db_ui_status(
            chat_id,
            api_base,
            "E2E_UPDATE_FINAL",
            timeout_sec=120.0,
        )

        reload_probe = await chat.evaluate(
            """(() => {
              location.reload();
              return { reloaded: true };
            })()""",
            await_promise=False,
            recv_timeout=15.0,
        )
        assert isinstance(reload_probe, dict)
        assert reload_probe.get("reloaded") is True
        await chat.ensure_chat_surface(BASE_URL)
        await _wait_js(
            chat,
            chat_id,
            _UPDATE_DATA_READY_JS,
            timeout_sec=180.0,
            error_label="page reload did not restore E2E_UPDATE_FINAL from persisted DB",
        )

        try:
            assert chat_user_message_count(chat_id, api_url=api_base) >= 2, (
                f"Expected two user messages for chat {chat_id}: ui={ui_state}"
            )
        except (TimeoutError, OSError, AssertionError) as exc:
            if ui_state.get("ready") is not True:
                raise AssertionError(
                    f"API message check failed and inline UI not ready: {exc}"
                ) from exc

        e2e_resource_ledger.register("chat", chat_id)
        return chat_id

    client = ChromeMcpClient(request_timeout_sec=120.0)
    await asyncio.to_thread(client.start)
    try:
        page: McpPage | None = None
        try:
            page = await asyncio.to_thread(client.new_page, BASE_URL, timeout_ms=120_000)
        except TimeoutError:
            await asyncio.sleep(2.0)
            page = await asyncio.to_thread(client.new_page, BASE_URL, timeout_ms=120_000)
        if page is None:
            raise RuntimeError("new_page returned no page")
        chat = McpChatSession(client, page)
        await chat.bootstrap(BASE_URL, timeout_sec=120.0)
        chat_id = await _run_flow(chat)
        assert chat_id
    finally:
        await asyncio.to_thread(client.close)
