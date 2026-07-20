"""Chrome E2E: desktop control approval via real WebUI SSE + Inspector banner.

Flow:
  enable computer_use → send agent message → desktop_interact triggers approval
  → click Allow once → tool resumes → assistant replies DONE.

Prerequisites:
  ./myrm ready --chrome  (macOS, Accessibility granted, provider ready)
"""

from __future__ import annotations

import asyncio
import json
import os
import platform
import subprocess
import sys
import urllib.request
from pathlib import Path

import pytest

_LIB = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from cdp_chat_support import chat_id_from_path, chat_messages_have_done, chat_user_message_count, get_e2e_api_url, wait_e2e_provider_ready  # noqa: E402
from chrome_mcp_client import ChromeMcpClient, McpPage  # noqa: E402
from mcp_chat_ui import McpChatSession  # noqa: E402

from tests.support.e2e_runtime_guard import E2EResourceLedger, heartbeat_e2e_lease

BASE_URL = os.getenv("E2E_UI_BASE", "http://127.0.0.1:3000").rstrip("/")
APPROVAL_WAIT_SEC = 240.0
TURN_WAIT_SEC = 300.0
MAX_SEND_ATTEMPTS_ONCE = 3
MAX_SEND_ATTEMPTS_ALWAYS = 2
_INFRA_ABORT_MARKERS = (
    "ECONNREFUSED",
    "Could not connect to Chrome",
    "Chrome MCP cleanup failed",
    "immutable test wave is not open",
    "E2E_WAVE_OPEN_FAILED",
    "E2E_RUNTIME_BINDING_FAILED",
    "LEASE_NOT_ACTIVE",
    "LEASE_CLEANUP_FAILED",
    "upstream request timed out",
    "connection reset",
    "detached Frame",
)
TEXTEDIT_FIXTURE_MARKER = "E2E desktop control scroll target line 1"
E2E_PROMPT = (
    f"TextEdit 已打开，文档含「{TEXTEDIT_FIXTURE_MARKER}」到 line 5。"
    "你必须调用 desktop_interact（ref 来自 snapshot 的 @dref，action=scroll，text=down）。"
    "禁止只调用 desktop_snapshot 或 desktop_vision 就结束。"
    "完成后只回复 DONE。"
)
E2E_NUDGE_PROMPT = (
    "请立即调用 desktop_interact（ref 来自上一个 snapshot 的 @dref，action=scroll，text=down）。"
    "不要只用 snapshot/vision。完成后只回复 DONE。"
)


def _max_send_attempts(scope: str) -> int:
    if scope == "always":
        return MAX_SEND_ATTEMPTS_ALWAYS
    return MAX_SEND_ATTEMPTS_ONCE


def _should_abort_desktop_e2e_retries(exc: BaseException) -> bool:
    message = str(exc)
    if any(marker in message for marker in _INFRA_ABORT_MARKERS):
        return True
    if isinstance(exc, ExceptionGroup):
        return any(_should_abort_desktop_e2e_retries(sub) for sub in exc.exceptions)
    return False


def _is_mux_new_page_retriable(exc: BaseException) -> bool:
    message = str(exc).lower()
    return (
        "upstream request timed out" in message
        or "tools/call error" in message and "timed out" in message
        or "transient_mux" in message
    )


async def _open_mcp_chat_page(client: ChromeMcpClient) -> McpPage:
    last_exc: BaseException | None = None
    for attempt in range(1, 4):
        heartbeat_e2e_lease()
        try:
            return await asyncio.to_thread(client.new_page, BASE_URL, timeout_ms=120_000)
        except (TimeoutError, RuntimeError) as exc:
            last_exc = exc
            if _should_abort_desktop_e2e_retries(exc) and not _is_mux_new_page_retriable(exc):
                raise
            if attempt >= 3 or not _is_mux_new_page_retriable(exc):
                raise
            _progress(f"new_page mux retry {attempt}/3 after: {exc}")
            await asyncio.sleep(5.0 * attempt)
    raise last_exc or RuntimeError("Chrome MCP new_page failed without exception")


def _require_approval_gate_triggered(
    *,
    last_tool: str,
    server_pending: int,
    ui_pending: bool,
) -> None:
    """Fail fast when the model never opened a pending desktop approval request."""
    if server_pending > 0 or ui_pending:
        return
    raise AssertionError(
        "Model never triggered desktop approval gate "
        f"(lastTool={last_tool!r}, server_pending={server_pending}). "
        "Expected desktop_interact_tool or desktop_vision_tool(scroll) with pending approval."
    )


async def _probe_desktop_tool_progress(chat: McpChatSession) -> dict[str, object]:
    probe = await chat.evaluate(
        """(() => window.__MYRM_E2E_CHAT__?.getDesktopToolProgress?.() ?? {})()""",
        await_promise=False,
    )
    return probe if isinstance(probe, dict) else {"active": False}


async def _wait_for_interact_or_approval(
    chat: McpChatSession,
    *,
    timeout_sec: float = 90.0,
) -> tuple[dict[str, object], str, int, bool]:
    deadline = asyncio.get_event_loop().time() + timeout_sec
    tool_activity: dict[str, object] = {"active": False}
    last_tool = ""
    server_pending = 0
    ui_pending = False
    while asyncio.get_event_loop().time() < deadline:
        heartbeat_e2e_lease()
        tool_activity = await _probe_desktop_tool_progress(chat)
        last_tool = str(tool_activity.get("lastTool") or "")
        server_pending = await asyncio.to_thread(_server_pending_approval_count)
        ui_pending = bool(tool_activity.get("pending"))
        if ui_pending or server_pending > 0 or last_tool.endswith("desktop_interact_tool"):
            return tool_activity, last_tool, server_pending, ui_pending
        await asyncio.sleep(1.0)
    return tool_activity, last_tool, server_pending, ui_pending


async def _ensure_interact_gate(
    chat: McpChatSession,
) -> tuple[dict[str, object], str, int, bool]:
    tool_activity = await chat.wait_desktop_tool_activity(timeout_sec=APPROVAL_WAIT_SEC)
    _progress(
        f"desktop tool activity result active={tool_activity.get('active')} "
        f"pending={tool_activity.get('pending')} lastTool={tool_activity.get('lastTool')} "
        f"err={tool_activity.get('err')}"
    )
    assert tool_activity.get("active") or tool_activity.get("pending"), (
        f"Model did not start desktop tools: {tool_activity}"
    )

    last_tool = str(tool_activity.get("lastTool") or "")
    server_pending = await asyncio.to_thread(_server_pending_approval_count)
    ui_pending = bool(tool_activity.get("pending"))
    snapshot_only = last_tool.endswith("desktop_snapshot_tool") or last_tool.endswith(
        "desktop_vision_tool"
    )
    if snapshot_only and not (ui_pending or server_pending > 0):
        _progress("snapshot-only detected; nudge interact immediately")
        try:
            await chat.send_message(E2E_NUDGE_PROMPT, E2E_NUDGE_PROMPT)
        except (RuntimeError, TimeoutError, OSError) as exc:
            raise AssertionError(f"Nudge send failed (Chrome mux): {exc}") from exc
        heartbeat_e2e_lease()
        tool_activity, last_tool, server_pending, ui_pending = await _wait_for_interact_or_approval(
            chat,
            timeout_sec=120.0,
        )
    elif not (ui_pending or server_pending > 0 or last_tool.endswith("desktop_interact_tool")):
        tool_activity, last_tool, server_pending, ui_pending = await _wait_for_interact_or_approval(
            chat,
            timeout_sec=45.0,
        )

    if not (ui_pending or server_pending > 0 or last_tool.endswith("desktop_interact_tool")):
        _progress("nudge model to call desktop_interact_tool")
        try:
            await chat.send_message(E2E_NUDGE_PROMPT, E2E_NUDGE_PROMPT)
        except (RuntimeError, TimeoutError, OSError) as exc:
            raise AssertionError(f"Nudge send failed (Chrome mux): {exc}") from exc
        heartbeat_e2e_lease()
        tool_activity, last_tool, server_pending, ui_pending = await _wait_for_interact_or_approval(
            chat,
            timeout_sec=120.0,
        )

    return tool_activity, last_tool, server_pending, ui_pending


def _progress(message: str) -> None:
    print(f"DESKTOP_E2E: {message}", file=sys.stderr, flush=True)


def _textedit_fixture_ready() -> bool:
    if platform.system() != "Darwin":
        return False
    proc = subprocess.run(
        [
            "osascript",
            "-e",
            'tell application "TextEdit"',
            "-e",
            "if not running then return false",
            "-e",
            "if (count of documents) is 0 then return false",
            "-e",
            f'return text of document 1 contains "{TEXTEDIT_FIXTURE_MARKER}"',
            "-e",
            "end tell",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    return proc.returncode == 0 and proc.stdout.strip().lower() == "true"


def _prepare_textedit_fixture() -> None:
    """Open TextEdit in the background and seed scrollable fixture text without stealing focus."""
    if platform.system() != "Darwin":
        return
    subprocess.run(
        ["open", "-gj", "-a", "TextEdit"],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    subprocess.run(
        [
            "osascript",
            "-e",
            'tell application "TextEdit"',
            "-e",
            "if not running then launch",
            "-e",
            "if (count of documents) is 0 then make new document",
            "-e",
            'set text of document 1 to "E2E desktop control scroll target line 1" & return & "E2E desktop control scroll target line 2" & return & "E2E desktop control scroll target line 3" & return & "E2E desktop control scroll target line 4" & return & "E2E desktop control scroll target line 5"',
            "-e",
            "end tell",
            "-e",
            'tell application "System Events" to tell process "TextEdit" to repeat with w in windows',
            "-e",
            "set miniaturized of w to true",
            "-e",
            "end repeat",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )


def _hide_textedit_fixture() -> None:
    """Keep the fixture reachable via AX without stealing user focus."""
    if platform.system() != "Darwin":
        return
    subprocess.run(
        [
            "osascript",
            "-e",
            'tell application "System Events" to tell process "TextEdit" to repeat with w in windows',
            "-e",
            "set miniaturized of w to true",
            "-e",
            "end repeat",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )


def _server_pending_approval_count() -> int:
    url = f"{get_e2e_api_url()}/webui/desktop/approval/pending"
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except OSError:
        return -1
    if not isinstance(payload, dict):
        return -1
    return int(payload.get("count") or 0)


def _list_trusted_apps_via_api() -> list[dict[str, object]]:
    url = f"{get_e2e_api_url()}/webui/desktop/trust/apps"
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except OSError as exc:
        raise AssertionError(f"Failed to list trusted apps: {exc}") from exc
    if not isinstance(payload, dict):
        raise AssertionError(f"Unexpected trust list payload: {payload!r}")
    apps = payload.get("apps")
    if not isinstance(apps, list):
        raise AssertionError(f"Unexpected trust list apps: {payload!r}")
    return apps


def _clear_persisted_desktop_approvals() -> None:
    data_dir = os.environ.get("MYRM_DATA_DIR", "").strip()
    if data_dir:
        approval_path = Path(data_dir) / ".agent" / "desktop_control" / "approved_apps.json"
        if approval_path.is_file():
            approval_path.unlink(missing_ok=True)
    reset_url = f"{get_e2e_api_url()}/webui/desktop/approval/reset-runtime"
    try:
        request = urllib.request.Request(reset_url, method="POST", data=b"{}")
        request.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except OSError as exc:
        _progress(f"desktop approval reset skipped: {exc}")
        return
    if not isinstance(payload, dict) or payload.get("ok") is not True:
        _progress(f"desktop approval reset unexpected response: {payload}")
        return
    try:
        apps = _list_trusted_apps_via_api()
        for app in apps:
            trust_key = str(app.get("trust_key") or "").strip()
            if not trust_key:
                continue
            revoke_request = urllib.request.Request(
                f"{get_e2e_api_url()}/webui/desktop/trust/apps",
                method="DELETE",
                data=json.dumps({"trust_key": trust_key}).encode("utf-8"),
            )
            revoke_request.add_header("Content-Type", "application/json")
            with urllib.request.urlopen(revoke_request, timeout=10):
                pass
    except OSError as exc:
        _progress(f"trusted apps clear skipped: {exc}")


async def _ensure_textedit_fixture_ready(*, attempts: int = 5) -> None:
    for attempt in range(1, attempts + 1):
        await asyncio.to_thread(_prepare_textedit_fixture)
        if await asyncio.to_thread(_textedit_fixture_ready):
            await asyncio.to_thread(_hide_textedit_fixture)
            _progress("textedit fixture ready (background, minimized)")
            return
        _progress(f"textedit fixture not ready yet ({attempt}/{attempts})")
        await asyncio.sleep(0.5)
    pytest.fail(
        "TextEdit fixture not ready — ensure TextEdit is installed and Accessibility is granted, then retry"
    )


def _desktop_accessibility_granted() -> bool:
    url = f"{get_e2e_api_url()}/webui/desktop/permissions"
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except OSError:
        return False
    return bool(payload.get("accessibility"))


def _activate_chrome() -> None:
    if platform.system() != "Darwin":
        return
    subprocess.run(
        ["osascript", "-e", 'tell application "Google Chrome" to activate'],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
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
    poll = 0
    nudged_done = False
    while asyncio.get_event_loop().time() < deadline:
        poll += 1
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
                matched: Boolean(snap.hasDone) || re.test(sample),
                lastAssistantSample: sample,
              }};
            }})()""",
            await_promise=False,
        )
        if isinstance(probe, dict):
            last = probe
            if poll == 1 or poll % 5 == 0:
                sample = str(probe.get("lastAssistantSample") or "")
                _progress(
                    f"poll DONE marker #{poll} streaming={probe.get('isStreaming')} "
                    f"matched={probe.get('matched')} sample_len={len(sample)}"
                )
            chat_id = str(probe.get("chatId") or chat_id_hint or "").strip()
            if (
                chat_id
                and int(probe.get("userCount") or 0) >= 1
                and not probe.get("isStreaming")
                and probe.get("matched")
            ):
                return {**probe, "chatId": chat_id}
            if chat_id and not probe.get("isStreaming"):
                api_has_done = await asyncio.to_thread(
                    chat_messages_have_done,
                    chat_id,
                    api_url=get_e2e_api_url(),
                )
                if api_has_done:
                    return {
                        **probe,
                        "chatId": chat_id,
                        "matched": True,
                        "mode": "post-approval-api-done",
                    }
            if (
                not nudged_done
                and poll >= 15
                and not probe.get("isStreaming")
                and not probe.get("matched")
                and int(probe.get("userCount") or 0) >= 1
            ):
                nudged_done = True
                _progress("nudge model to reply DONE only")
                await chat.send_message("Reply with only DONE.", "Reply with only DONE.")
                heartbeat_e2e_lease()
                continue
        await asyncio.sleep(2.0)
    return {**last, "ok": False, "err": "turn-timeout"}


async def _wait_for_trusted_app_display_name(
    display_name: str,
    *,
    timeout_sec: float = 60.0,
) -> dict[str, object]:
    deadline = asyncio.get_event_loop().time() + timeout_sec
    target = display_name.strip().lower()
    poll = 0
    apps: list[dict[str, object]] = []
    while asyncio.get_event_loop().time() < deadline:
        poll += 1
        heartbeat_e2e_lease()
        apps = await asyncio.to_thread(_list_trusted_apps_via_api)
        for app in apps:
            if not isinstance(app, dict):
                continue
            name = str(app.get("display_name") or "").strip().lower()
            if name == target or target in name:
                return app
        if apps and poll % 5 == 0:
            _progress(f"trust API poll waiting for {display_name!r}: {apps}")
        await asyncio.sleep(1.0)
    raise AssertionError(
        f"Trusted app {display_name!r} not found via API within {timeout_sec}s: {apps}"
    )


async def _verify_settings_revoke_trusted_app(
    chat: McpChatSession,
    *,
    trust_key: str,
    display_name: str,
) -> None:
    settings_url = f"{BASE_URL}/settings/system"
    _progress(f"open settings for revoke trust_key={trust_key}")
    nav = await chat.evaluate(
        f"""(() => {{
          window.location.assign({settings_url!r});
          return {{ ok: true }};
        }})()""",
        await_promise=False,
    )
    assert isinstance(nav, dict) and nav.get("ok") is True, nav

    deadline = asyncio.get_event_loop().time() + 120.0
    while asyncio.get_event_loop().time() < deadline:
        heartbeat_e2e_lease()
        probe = await chat.evaluate(
            f"""(() => {{
              const body = document.body?.innerText || '';
              const revokeBtn = document.querySelector('[data-testid="desktop-trust-revoke-{trust_key}"]');
              return {{
                hasDisplayName: body.includes({display_name!r}),
                revokeReady: Boolean(revokeBtn && !revokeBtn.disabled),
              }};
            }})()""",
            await_promise=False,
        )
        if isinstance(probe, dict) and probe.get("hasDisplayName") and probe.get("revokeReady"):
            break
        await asyncio.sleep(1.0)
    else:
        raise AssertionError(f"Settings trusted-app row not ready for revoke: {probe}")

    click = await chat.evaluate(
        f"""(() => {{
          const btn = document.querySelector('[data-testid="desktop-trust-revoke-{trust_key}"]');
          if (!btn || btn.disabled) return {{ ok: false, err: 'revoke-not-ready' }};
          btn.click();
          return {{ ok: true }};
        }})()""",
        await_promise=False,
    )
    assert isinstance(click, dict) and click.get("ok") is True, f"Settings revoke click failed: {click}"

    empty_deadline = asyncio.get_event_loop().time() + 60.0
    while asyncio.get_event_loop().time() < empty_deadline:
        heartbeat_e2e_lease()
        apps = await asyncio.to_thread(_list_trusted_apps_via_api)
        if not apps:
            return
        await asyncio.sleep(1.0)
    raise AssertionError(f"Trusted apps not empty after settings revoke: {apps}")


async def _complete_turn_after_approval(
    chat: McpChatSession,
    *,
    chat_id_hint: str | None,
) -> str:
    _progress("wait assistant DONE")
    after_turn = await _wait_stream_done_with_marker(
        chat,
        chat_id_hint=chat_id_hint,
        marker="DONE",
        timeout_sec=180.0,
    )
    if not after_turn.get("matched"):
        chat_id_probe = str(after_turn.get("chatId") or chat_id_hint or "").strip()
        if chat_id_probe and await asyncio.to_thread(
            chat_messages_have_done,
            chat_id_probe,
            api_url=get_e2e_api_url(),
        ):
            _progress("approval verified via API DONE marker fallback")
            after_turn = {
                **after_turn,
                "matched": True,
                "chatId": chat_id_probe,
                "mode": "post-approval-api-done",
            }

    if str(after_turn.get("path", "")).startswith("/settings"):
        pytest.fail(f"Send redirected to settings: {after_turn}")
    assert after_turn.get("matched") is True, (
        f"Turn did not complete with DONE after approval: {after_turn}"
    )

    chat_id = await _resolve_chat_id(chat, after_turn)
    assert chat_id, f"Expected chat id after approval turn: {after_turn}"
    assert chat_user_message_count(chat_id) >= 1, after_turn
    _progress(f"done chat_id={chat_id}")
    return chat_id


async def _run_approval_attempt(chat: McpChatSession, *, scope: str = "once") -> str:
    _progress("new chat + ensure surface")
    await chat.click_new_chat()
    await chat.ensure_chat_surface(BASE_URL)
    await _ensure_textedit_fixture_ready()

    _progress("enable computer_use")
    tools_setup = await chat.enable_computer_use()
    assert tools_setup.get("ok") is True, f"computer_use bridge failed: {tools_setup}"
    assert "computer_use" in (tools_setup.get("tools") or []), tools_setup

    heartbeat_e2e_lease()
    _progress("send agent prompt (textedit stays minimized; no focus loop)")
    await chat.send_message(E2E_PROMPT, E2E_PROMPT)
    heartbeat_e2e_lease()

    _progress("wait desktop tool activity")
    tool_activity, last_tool, server_pending, ui_pending = await _ensure_interact_gate(chat)
    _progress(
        f"post-wait lastTool={last_tool} server_pending={server_pending} ui_pending={ui_pending}"
    )
    _require_approval_gate_triggered(
        last_tool=last_tool,
        server_pending=server_pending,
        ui_pending=ui_pending,
    )

    _progress("activate chrome for approval UI")
    await asyncio.to_thread(_activate_chrome)
    await asyncio.sleep(1.0)

    _progress("wait approval banner")
    approval_deadline = asyncio.get_event_loop().time() + APPROVAL_WAIT_SEC
    approval: dict[str, object] = {"pending": False}
    poll = 0
    while asyncio.get_event_loop().time() < approval_deadline:
        poll += 1
        heartbeat_e2e_lease()
        server_pending = await asyncio.to_thread(_server_pending_approval_count)
        probe = await chat.probe_desktop_approval_once()
        if isinstance(probe, dict):
            approval = probe
            if poll == 1 or poll % 10 == 0:
                _progress(
                    f"approval poll #{poll} ui_pending={probe.get('pending')} "
                    f"allowVisible={probe.get('allowVisible')} server_pending={server_pending}"
                )
            if probe.get("pending") or probe.get("allowVisible"):
                break
            if server_pending > 0:
                await asyncio.sleep(0.5)
                continue
            if probe.get("err") == "model-completed-without-desktop-tools":
                raise AssertionError(f"Model finished without desktop tools: {probe}")
        await asyncio.sleep(0.5)

    if approval.get("err") == "model-completed-without-desktop-tools":
        raise AssertionError(f"Model finished without desktop tools: {approval}")
    assert approval.get("pending") is True or approval.get("allowVisible") is True, (
        f"Expected desktop approval banner (server_pending="
        f"{await asyncio.to_thread(_server_pending_approval_count)}): {approval}"
    )
    if not approval.get("allowVisible"):
        allow_deadline = asyncio.get_event_loop().time() + 30.0
        while asyncio.get_event_loop().time() < allow_deadline:
            probe = await chat.probe_desktop_approval_once()
            if isinstance(probe, dict) and probe.get("allowVisible"):
                approval = probe
                break
            await asyncio.sleep(0.25)
    if not approval.get("allowVisible"):
        allow_deadline = asyncio.get_event_loop().time() + 30.0
        while asyncio.get_event_loop().time() < allow_deadline:
            probe = await chat.probe_desktop_approval_once()
            if isinstance(probe, dict) and probe.get("allowVisible"):
                approval = probe
                break
            await asyncio.sleep(0.25)
    assert approval.get("allowVisible") is True, f"Allow-once button not visible: {approval}"

    if scope == "always":
        if not approval.get("allowAlwaysVisible"):
            always_deadline = asyncio.get_event_loop().time() + 30.0
            while asyncio.get_event_loop().time() < always_deadline:
                probe = await chat.probe_desktop_approval_once()
                if isinstance(probe, dict) and probe.get("allowAlwaysVisible"):
                    approval = probe
                    break
                await asyncio.sleep(0.25)
        assert approval.get("allowAlwaysVisible") is True, (
            f"Allow-always button not visible: {approval}"
        )
        _progress("click allow always")
        click = await chat.click_desktop_allow_always()
        assert click.get("ok") is True, f"Allow-always click failed: {click}"
    else:
        _progress("click allow once")
        click = await chat.click_desktop_allow_once()
        assert click.get("ok") is True, f"Allow-once click failed: {click}"

    chat_id_hint = str(
        (await chat.evaluate(
            "(() => window.__MYRM_E2E_CHAT__?.turnSnapshot?.()?.chatId ?? null)()",
            await_promise=False,
        ))
        or ""
    ).strip() or None

    trusted: dict[str, object] | None = None
    if scope == "always":
        trusted = await _wait_for_trusted_app_display_name("TextEdit", timeout_sec=120.0)

    chat_id = await _complete_turn_after_approval(chat, chat_id_hint=chat_id_hint)

    if scope == "always":
        assert trusted is not None
        trust_key = str(trusted.get("trust_key") or "").strip()
        assert trust_key, f"Missing trust_key in trusted app record: {trusted}"
        await _verify_settings_revoke_trusted_app(
            chat,
            trust_key=trust_key,
            display_name="TextEdit",
        )

    return chat_id


async def _run_desktop_approval_chrome_e2e(
    *,
    scope: str,
    label: str,
    e2e_resource_ledger: E2EResourceLedger,
) -> None:
    if not wait_e2e_provider_ready():
        pytest.fail(
            "Provider config not ready for live E2E — run via ./myrm test -m chrome_e2e "
            "after ./myrm ready --chrome"
        )
    if not _desktop_accessibility_granted():
        pytest.fail(
            "macOS Accessibility permission is not granted for the backend — "
            "open System Settings → Privacy & Security → Accessibility and allow Cursor/Terminal, "
            "then retry after ./myrm restart --chrome"
        )

    await _ensure_textedit_fixture_ready()
    _clear_persisted_desktop_approvals()

    async def run_flow(chat: McpChatSession) -> str:
        await chat.bootstrap(BASE_URL, navigate=False, timeout_sec=120.0)

        last_error: dict[str, object] | None = None
        max_attempts = _max_send_attempts(scope)
        for attempt in range(1, max_attempts + 1):
            heartbeat_e2e_lease()
            _progress(f"{label} attempt {attempt}/{max_attempts}")
            _clear_persisted_desktop_approvals()
            try:
                chat_id = await _run_approval_attempt(chat, scope=scope)
                e2e_resource_ledger.register("chat", chat_id)
                return chat_id
            except (AssertionError, RuntimeError, TimeoutError, OSError) as exc:
                last_error = {"attempt": attempt, "error": str(exc), "type": type(exc).__name__}
                if _should_abort_desktop_e2e_retries(exc):
                    pytest.fail(
                        "Desktop approval Chrome E2E hit non-retriable infra failure "
                        f"(api={get_e2e_api_url()}): {last_error}. "
                        "Parallel tests should queue via E2E_LEASE_WAIT; "
                        "orchestrator heal (wave/mux) is required — not user cleanup."
                    )
                if attempt >= max_attempts:
                    break
                try:
                    await chat.ensure_e2e_api_base_binding()
                    await chat._ensure_react_e2e_bridge(timeout_sec=90.0)
                    await chat.click_new_chat()
                    await chat.ensure_chat_surface(BASE_URL)
                except (RuntimeError, TimeoutError, OSError) as reset_exc:
                    if _should_abort_desktop_e2e_retries(reset_exc):
                        pytest.fail(
                            "Desktop approval Chrome E2E lost UI bridge during retry "
                            f"(api={get_e2e_api_url()}): {last_error}; reset={reset_exc}"
                        )
                await asyncio.sleep(2.0)

        pytest.fail(
            f"Desktop approval Chrome E2E ({label}) failed after {max_attempts} attempts "
            f"(api={get_e2e_api_url()}): {last_error}"
        )

    client = ChromeMcpClient(request_timeout_sec=180.0)
    await asyncio.to_thread(client.start)
    try:
        page = await _open_mcp_chat_page(client)
        chat = McpChatSession(client, page)
        await run_flow(chat)
    finally:
        try:
            client.close()
        except BaseException as exc:
            if not _should_abort_desktop_e2e_retries(exc):
                raise
            _progress(f"Chrome MCP cleanup skipped after infra failure: {exc}")
        await asyncio.to_thread(_hide_textedit_fixture)


@pytest.mark.chrome_e2e(lane="LIVE_AGENT", private_backend=False)
@pytest.mark.chrome_e2e_desktop
@pytest.mark.integration
@pytest.mark.timeout(1800)
@pytest.mark.skipif(platform.system() != "Darwin", reason="macOS computer_use only")
@pytest.mark.asyncio
async def test_chrome_ui_desktop_control_approval_allow_once(
    e2e_resource_ledger: E2EResourceLedger,
) -> None:
    await _run_desktop_approval_chrome_e2e(
        scope="once",
        label="allow-once",
        e2e_resource_ledger=e2e_resource_ledger,
    )


@pytest.mark.chrome_e2e(lane="LIVE_AGENT", private_backend=False)
@pytest.mark.chrome_e2e_desktop
@pytest.mark.integration
@pytest.mark.timeout(2400)
@pytest.mark.skipif(platform.system() != "Darwin", reason="macOS computer_use only")
@pytest.mark.asyncio
async def test_chrome_ui_desktop_control_approval_allow_always_settings_revoke(
    e2e_resource_ledger: E2EResourceLedger,
) -> None:
    await _run_desktop_approval_chrome_e2e(
        scope="always",
        label="allow-always-settings-revoke",
        e2e_resource_ledger=e2e_resource_ledger,
    )
