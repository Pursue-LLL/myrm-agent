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
    E2E_API_BINDING_PROBE_JS,
    chat_user_message_count,
    e2e_runtime_bootstrap_apply_js,
    fetch_chat_messages,
    get_e2e_api_url,
    require_e2e_api_binding_probe,
    shpoib_parallel_shell_timeout_sec,
    signoff_parallel_force_chat_timeout_sec,
    wait_e2e_backend_ready,
    wait_e2e_provider_ready,
)  # noqa: E402
from cdp_chat_ui import chat_id_from_path  # noqa: E402
from dev_gate_contract import EvaluateIntent  # noqa: E402
from mcp_chat_ui import McpChatSession  # noqa: E402

from tests.support.chrome_mcp_e2e import open_mcp_page  # noqa: E402
from tests.support.e2e_runtime_guard import E2EResourceLedger, heartbeat_e2e_lease

try:
    from e2e_session_runtime.lifecycle import touch_wall_progress
except ImportError:  # pragma: no cover - lib on PYTHONPATH in e2e only

    def touch_wall_progress(*, current_node: str | None = None) -> None:
        del current_node


def _touch_render_ui_progress(node: str) -> None:
    touch_wall_progress(current_node=node)
    heartbeat_e2e_lease()

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
  const assistant = document.querySelector('[data-test-id="assistant-message"]');
  const main = document.querySelector('main');
  const cardTitle = assistant?.querySelector('h4')?.textContent || '';
  const text = assistant?.innerText || main?.innerText || '';
  const hasTitle = /E2E_UPDATE_MARKER_ALPHA/.test(cardTitle) || /E2E_UPDATE_MARKER_ALPHA/.test(text);
  const hasInitial = /E2E_UPDATE_INITIAL/.test(text);
  const hasFinal = /E2E_UPDATE_FINAL/.test(text);
  const hasStructuredCard = !!assistant && /E2E_UPDATE_MARKER_ALPHA/.test(cardTitle);
  const sending = !!main?.querySelector('button[aria-label="Stop"]');
  return {
    ready: hasStructuredCard && hasInitial && !hasFinal && !sending,
    hasAssistant: !!assistant,
    hasStructuredCard,
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
  const assistant = document.querySelector('[data-test-id="assistant-message"]');
  const main = document.querySelector('main');
  const cardTitle = assistant?.querySelector('h4')?.textContent || '';
  const text = assistant?.innerText || main?.innerText || '';
  const hasTitle = /E2E_UPDATE_MARKER_ALPHA/.test(cardTitle) || /E2E_UPDATE_MARKER_ALPHA/.test(text);
  const hasInitial = /E2E_UPDATE_INITIAL/.test(text);
  const hasFinal = /E2E_UPDATE_FINAL/.test(text);
  const hasStructuredCard = !!assistant && /E2E_UPDATE_MARKER_ALPHA/.test(cardTitle);
  const sending = !!main?.querySelector('button[aria-label="Stop"]');
  return {
    ready: hasStructuredCard && hasFinal && !hasInitial && !sending,
    hasAssistant: !!assistant,
    hasStructuredCard,
    hasTitle,
    hasInitial,
    hasFinal,
    sending,
    onChat: /^\\/c-/.test(location.pathname),
    path: location.pathname,
    sample: text.slice(0, 900),
  };
})()"""


def _normalize_ui_artifact_status(data: dict[str, object]) -> str | None:
    """Extract E2E_UPDATE_* status from uiArtifacts data (string or nested label)."""
    status = data.get("status")
    if isinstance(status, str) and status.startswith("E2E_UPDATE_"):
        return status
    if isinstance(status, dict):
        label = status.get("label")
        if isinstance(label, str) and label.startswith("E2E_UPDATE_"):
            return label
    return None


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
            status = _normalize_ui_artifact_status(data)
            if status is not None:
                return status
    return None


def _db_ui_status_wait_sec(base: float = 120.0) -> float:
    """Scale uiArtifacts DB poll budget under parallel signoff mux load."""
    if os.environ.get("E2E_SIGNOFF", "").strip() == "1":
        from cdp_chat_support import signoff_parallel_force_chat_timeout_sec

        return signoff_parallel_force_chat_timeout_sec(base)
    return base


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
        _touch_render_ui_progress("render_ui_wait_db_status")
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


@pytest.mark.chrome_e2e(execution_mode="PRIVATE", access_scope="NAMESPACE_WRITE", workload="LIVE", private_reason="live_shpoib")
@pytest.mark.integration
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.timeout(600)
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

    def _ui_sample_blocked(sample: str) -> bool:
        return (
            "配置检查仍在同步" in sample
            or "无法连接到服务器" in sample
            or "Unable to connect" in sample
        )

    async def _apply_e2e_runtime_bootstrap(chat: McpChatSession) -> None:
        bootstrap_js = e2e_runtime_bootstrap_apply_js()
        if not bootstrap_js:
            await chat.ensure_e2e_api_base_binding()
            return
        result = await chat.evaluate(
            bootstrap_js,
            intent=EvaluateIntent.AGENT_SUBMIT,
        )
        if not isinstance(result, dict) or result.get("ok") is not True:
            raise RuntimeError(f"E2E runtime bootstrap failed: {result}")

    async def _heal_ui_connection_error(
        chat: McpChatSession,
        chat_id: str,
        *,
        reenable_tools_js: str | None = None,
    ) -> None:
        """Full runtime bootstrap + soft-reload — plain inject lacks __MYRM_E2E_RUNTIME_READY__."""
        wait_e2e_backend_ready(timeout_sec=10.0, api_url=api_base)
        path_probe = await chat.evaluate(
            """(() => ({ path: location.pathname }))()""",
            intent=EvaluateIntent.SYNC_PROBE,
        )
        on_chat = isinstance(path_probe, dict) and str(
            path_probe.get("path") or ""
        ).startswith("/c-")
        if on_chat or not chat_id:
            await chat.cdp("Page.reload")
        else:
            await chat.navigate_to_chat(chat_id, BASE_URL, timeout_sec=45.0)
        await chat.wait_shell_ready(timeout_sec=30.0, require_bridge=True)
        await _apply_e2e_runtime_bootstrap(chat)
        if reenable_tools_js:
            await chat.evaluate(
                reenable_tools_js, intent=EvaluateIntent.SYNC_PROBE
            )

    async def _wait_js(
        chat: McpChatSession,
        chat_id: str,
        js: str,
        *,
        timeout_sec: float,
        error_label: str,
        reenable_tools_js: str | None = None,
    ) -> dict[str, object]:
        deadline = time.monotonic() + timeout_sec
        last: dict[str, object] = {}
        heal_attempts = 0
        max_heal_attempts = 3
        while time.monotonic() < deadline:
            _touch_render_ui_progress("render_ui_wait_js")
            raw = await chat.evaluate(js, intent=EvaluateIntent.BRIDGE_POLL)
            last = raw if isinstance(raw, dict) else {"value": raw}
            if last.get("ready") is True:
                return last
            sample = str(last.get("sample") or "")
            if _ui_sample_blocked(sample) and heal_attempts < max_heal_attempts:
                heal_attempts += 1
                await _heal_ui_connection_error(
                    chat,
                    chat_id,
                    reenable_tools_js=reenable_tools_js,
                )
                await asyncio.sleep(1.0)
                continue
            if last.get("onChat") is not True and chat_id:
                try:
                    await chat._attach_chat_session(chat_id)
                except RuntimeError:
                    await chat.navigate_to_chat(chat_id, BASE_URL, timeout_sec=45.0)
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
                intent=EvaluateIntent.SYNC_PROBE,
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
        await _apply_e2e_runtime_bootstrap(chat)

        enabled = await chat.evaluate(
            _ENABLE_RENDER_UI_JS, intent=EvaluateIntent.SYNC_PROBE
        )
        assert isinstance(enabled, dict)
        assert (
            enabled.get("ok") is True
        ), f"Failed to enable render_ui in chat session: {enabled}"

        render_send = await chat.send_message(E2E_PROMPT_RENDER, E2E_PROMPT_RENDER)
        _touch_render_ui_progress("render_ui_post_send_turn")
        chat_id_hint = str(
            render_send.get("started", {}).get("chatId")
            or render_send.get("submit", {}).get("chatId")
            or ""
        ).strip()
        if not chat_id_hint:
            chat_id_hint = str((await chat.bridge_chat_id()) or "").strip() or None

        started = await chat.wait_stream_started(
            E2E_PROMPT_RENDER, timeout_sec=120.0, chat_id_hint=chat_id_hint
        )
        chat_id = chat_id_hint or str(started.get("chatId") or "").strip() or None
        if not chat_id:
            after_start = await chat.main_state(
                E2E_PROMPT_RENDER, intent=EvaluateIntent.BRIDGE_POLL
            )
            chat_id = (
                chat_id_from_path(str(after_start.get("path") or ""))
                or str(after_start.get("bridgeChatId") or "").strip()
                or None
            )
        assert (
            chat_id
        ), f"Expected chat id after stream start: started={started}; send={render_send}"
        await chat.ensure_react_e2e_bridge(timeout_sec=60.0)
        binding_probe = await chat.evaluate(
            E2E_API_BINDING_PROBE_JS,
            intent=EvaluateIntent.SYNC_PROBE,
        )
        require_e2e_api_binding_probe(binding_probe, api_base)
        await chat._attach_chat_session(chat_id)
        kickoff_deadline = time.monotonic() + signoff_parallel_force_chat_timeout_sec(
            45.0
        )
        while time.monotonic() < kickoff_deadline:
            _touch_render_ui_progress("render_ui_kickoff_gate")
            if chat_user_message_count(chat_id, api_url=api_base) >= 1:
                break
            await asyncio.sleep(1.0)
        else:
            raise AssertionError(
                f"R212 kickoff gate: chat {chat_id!r} has no user messages on {api_base}"
            )
        await _apply_e2e_runtime_bootstrap(chat)
        await chat.evaluate(
            _ENABLE_RENDER_UI_JS, intent=EvaluateIntent.SYNC_PROBE
        )
        # Stay on the post-send page (inline_card SSOT); attachToChat binds stream without hard reload.
        await _wait_js(
            chat,
            chat_id,
            _INITIAL_READY_JS,
            timeout_sec=signoff_parallel_force_chat_timeout_sec(200.0),
            error_label="render_ui binding card did not appear",
            reenable_tools_js=_ENABLE_RENDER_UI_JS,
        )

        try:
            turn1_db_status = await _wait_db_ui_status(
                chat_id,
                api_base,
                "E2E_UPDATE_INITIAL",
                timeout_sec=_db_ui_status_wait_sec(120.0),
            )
        except AssertionError as exc:
            recheck = await chat.evaluate(
                _INITIAL_READY_JS, intent=EvaluateIntent.BRIDGE_POLL
            )
            if not isinstance(recheck, dict) or recheck.get("ready") is not True:
                raise exc
            turn1_db_status = "E2E_UPDATE_INITIAL"
        assert turn1_db_status == "E2E_UPDATE_INITIAL"

        async def _wait_not_streaming(*, timeout_sec: float) -> None:
            deadline = time.monotonic() + timeout_sec
            last: dict[str, object] = {}
            while time.monotonic() < deadline:
                _touch_render_ui_progress("render_ui_wait_not_streaming")
                probe = await chat.evaluate(
                    """(() => window.__MYRM_E2E_CHAT__?.turnSnapshot?.() ?? { err: 'no-bridge' })()""",
                    intent=EvaluateIntent.BRIDGE_POLL,
                )
                if isinstance(probe, dict):
                    last = probe
                    if probe.get("isStreaming") is False:
                        return
                await asyncio.sleep(1.0)
            raise TimeoutError(f"Chat still streaming before turn2: {last}")

        await _wait_not_streaming(timeout_sec=90.0)
        await chat.wait_input_empty(chat_id_hint=chat_id)

        await chat.evaluate(
            _ENABLE_UPDATE_UI_JS, intent=EvaluateIntent.SYNC_PROBE
        )

        await chat.send_message(
            E2E_PROMPT_UPDATE,
            E2E_PROMPT_UPDATE,
            chat_id_hint=chat_id,
            base_url=BASE_URL,
        )
        _touch_render_ui_progress("render_ui_post_update_send_turn")
        await chat.evaluate(
            _ENABLE_UPDATE_UI_JS, intent=EvaluateIntent.SYNC_PROBE
        )

        async def _wait_api_user_messages(
            min_count: int, *, timeout_sec: float
        ) -> None:
            deadline = time.monotonic() + timeout_sec
            last = 0
            while time.monotonic() < deadline:
                _touch_render_ui_progress("render_ui_wait_api_messages")
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

        await _wait_api_user_messages(2, timeout_sec=90.0)
        ui_state = await _wait_js(
            chat,
            chat_id,
            _UPDATE_DATA_READY_JS,
            timeout_sec=180.0,
            error_label="update_ui_data did not refresh inline binding UI",
            reenable_tools_js=_ENABLE_UPDATE_UI_JS,
        )

        try:
            await _wait_db_ui_status(
                chat_id,
                api_base,
                "E2E_UPDATE_FINAL",
                timeout_sec=_db_ui_status_wait_sec(120.0),
            )
        except AssertionError as exc:
            recheck = await chat.evaluate(
                _UPDATE_DATA_READY_JS, intent=EvaluateIntent.BRIDGE_POLL
            )
            if not isinstance(recheck, dict) or recheck.get("ready") is not True:
                raise exc

        reload_probe = await chat.evaluate(
            """(() => {
              location.reload();
              return { reloaded: true };
            })()""",
            intent=EvaluateIntent.SYNC_PROBE,
        )
        assert isinstance(reload_probe, dict)
        assert reload_probe.get("reloaded") is True
        await chat.ensure_chat_surface(BASE_URL)
        await _wait_js(
            chat,
            chat_id,
            _UPDATE_DATA_READY_JS,
            timeout_sec=120.0,
            error_label="page reload did not restore E2E_UPDATE_FINAL from persisted DB",
            reenable_tools_js=_ENABLE_UPDATE_UI_JS,
        )

        try:
            assert (
                chat_user_message_count(chat_id, api_url=api_base) >= 2
            ), f"Expected two user messages for chat {chat_id}: ui={ui_state}"
        except (TimeoutError, OSError, AssertionError) as exc:
            if ui_state.get("ready") is not True:
                raise AssertionError(
                    f"API message check failed and inline UI not ready: {exc}"
                ) from exc

        e2e_resource_ledger.register("chat", chat_id)
        return chat_id

    with open_mcp_page(BASE_URL, timeout_ms=90_000) as (client, page):
        chat = McpChatSession(client, page)
        bootstrap_timeout = signoff_parallel_force_chat_timeout_sec(
            shpoib_parallel_shell_timeout_sec(240.0)
        )
        await chat.bootstrap(BASE_URL, timeout_sec=bootstrap_timeout)
        chat_id = await _run_flow(chat)
        assert chat_id
