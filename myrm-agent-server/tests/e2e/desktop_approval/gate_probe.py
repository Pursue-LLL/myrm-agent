"""Desktop interact gate probing for approval Chrome E2E."""

from __future__ import annotations

import asyncio

from cdp_chat_support import fetch_provider_readiness_snapshot, get_e2e_api_url
from mcp_chat_ui import McpChatSession

from tests.e2e.desktop_approval.constants import (
    APPROVAL_WAIT_SEC,
    E2E_NUDGE_PROMPT,
    E2E_SNAPSHOT_NUDGE_PROMPT,
    GATE_IDLE_FAIL_FAST_SEC,
    build_desktop_interact_nudge,
    progress,
)
from tests.e2e.desktop_approval.textedit_fixture import activate_chrome_foreground
from tests.e2e.desktop_approval.trust_api import (
    fetch_desktop_tool_progress_from_api,
    server_pending_approval_count,
)
from tests.support.e2e_runtime_guard import heartbeat_e2e_lease


def _desktop_gate_satisfied(
    *,
    last_tool: str,
    server_pending: int,
    ui_pending: bool,
) -> bool:
    return ui_pending or server_pending > 0 or last_tool.endswith("desktop_interact_tool")


_PENDING_API_FAIL_ABORT_STREAK = 20


async def _resolve_server_pending(*, api_fail_streak: list[int]) -> int:
    count = await asyncio.to_thread(server_pending_approval_count)
    if count >= 0:
        if api_fail_streak[0] > 0:
            progress(f"backend pending API recovered after {api_fail_streak[0]} blips")
        api_fail_streak[0] = 0
        return count
    api_fail_streak[0] += 1
    if api_fail_streak[0] == 1 or api_fail_streak[0] % 5 == 0:
        progress(
            f"backend pending API blip #{api_fail_streak[0]} "
            f"(abort after {_PENDING_API_FAIL_ABORT_STREAK})"
        )
    if api_fail_streak[0] >= _PENDING_API_FAIL_ABORT_STREAK:
        hint = await _provider_readiness_hint()
        raise AssertionError(
            "Desktop approval E2E API unreachable "
            f"at {get_e2e_api_url()} (pending probe failed {api_fail_streak[0]} times)."
            f"{hint}"
        )
    return count


async def _provider_readiness_hint() -> str:
    snapshot = await asyncio.to_thread(fetch_provider_readiness_snapshot)
    provider = snapshot.get("provider")
    if isinstance(provider, dict):
        return (
            f" provider.is_ready={provider.get('is_ready')!r}"
            f" provider.model={provider.get('model')!r}"
            f" provider.error={provider.get('error')!r}"
        )
    return f" provider_readiness={snapshot!r}"


def require_approval_gate_triggered(
    *,
    last_tool: str,
    server_pending: int,
    ui_pending: bool,
    provider_hint: str = "",
) -> None:
    """Fail fast when the model never opened a pending desktop approval request."""
    if _desktop_gate_satisfied(
        last_tool=last_tool,
        server_pending=server_pending,
        ui_pending=ui_pending,
    ):
        return
    raise AssertionError(
        "Model never triggered desktop approval gate "
        f"(lastTool={last_tool!r}, server_pending={server_pending}, ui_pending={ui_pending}). "
        "Expected desktop_interact_tool with pending approval."
        f"{provider_hint}"
    )


async def probe_desktop_tool_progress(
    chat: McpChatSession,
    *,
    chat_id: str = "",
    api_only: bool = False,
) -> dict[str, object]:
    normalized_chat_id = chat_id.strip()
    if api_only and normalized_chat_id:
        api_probe = await asyncio.to_thread(fetch_desktop_tool_progress_from_api, normalized_chat_id)
        return api_probe if isinstance(api_probe, dict) else {"active": False}
    probe = await chat.evaluate(
        """(() => window.__MYRM_E2E_CHAT__?.getDesktopToolProgress?.() ?? {})()""",
        await_promise=False,
    )
    ui_probe = probe if isinstance(probe, dict) else {"active": False}
    if not normalized_chat_id:
        normalized_chat_id = await _bridge_chat_id(chat)
    api_probe = (
        await asyncio.to_thread(fetch_desktop_tool_progress_from_api, normalized_chat_id)
        if normalized_chat_id
        else None
    )
    return _merge_desktop_progress(ui_probe, api_probe)


async def _bridge_chat_id(chat: McpChatSession) -> str:
    chat_id = await chat.evaluate(
        """(() => window.__MYRM_E2E_CHAT__?.turnSnapshot?.()?.chatId ?? '')()""",
        await_promise=False,
    )
    return str(chat_id or "").strip()


def _merge_desktop_progress(
    ui_probe: dict[str, object],
    api_probe: dict[str, object] | None,
) -> dict[str, object]:
    if api_probe is None:
        return ui_probe
    ui_last = str(ui_probe.get("lastTool") or "")
    api_last = str(api_probe.get("lastTool") or "")
    ui_steps = int(ui_probe.get("stepCount") or 0)
    api_steps = int(api_probe.get("stepCount") or 0)
    prefer_api = api_steps > ui_steps or (api_last.startswith("desktop_") and not ui_last.startswith("desktop_"))
    merged: dict[str, object] = dict(ui_probe)
    if prefer_api:
        merged.update(api_probe)
    elif api_probe.get("completionStatus") == "complete" and ui_probe.get("isStreaming"):
        merged["isStreaming"] = False
        merged["assistantSample"] = api_probe.get("assistantSample") or ui_probe.get("assistantSample")
        merged["completionStatus"] = api_probe.get("completionStatus")
    merged["uiLastTool"] = ui_last
    merged["apiLastTool"] = api_last
    return merged


async def _abort_stuck_ui_stream(chat: McpChatSession) -> None:
    await chat.evaluate(
        """(() => {
          window.__MYRM_E2E_CHAT__?.abortActiveStream?.();
          return { ok: true };
        })()""",
        await_promise=False,
    )


async def _fetch_first_desktop_dref(
    chat: McpChatSession,
    *,
    last_tool: str = "",
) -> str | None:
    probe = await chat.evaluate(
        """(() => window.__MYRM_E2E_CHAT__?.getFirstDesktopDref?.() ?? null)()""",
        await_promise=False,
    )
    if probe is not None:
        normalized = str(probe).strip().lstrip("@")
        if normalized.startswith("d") and len(normalized) > 1:
            return normalized
    if last_tool.endswith("desktop_snapshot_tool"):
        progress("dref fallback to d0 after desktop_snapshot_tool")
        return "d0"
    return None


async def _send_interact_nudge(
    chat: McpChatSession,
    *,
    last_tool: str,
) -> None:
    dref: str | None = None
    if last_tool.endswith("desktop_snapshot_tool"):
        await asyncio.sleep(1.0)
        dref = await _fetch_first_desktop_dref(chat, last_tool=last_tool)
    if dref:
        progress(f"nudge with concrete dref={dref!r}")
        nudge_prompt = build_desktop_interact_nudge(dref=dref)
    elif last_tool.endswith("desktop_snapshot_tool"):
        nudge_prompt = E2E_SNAPSHOT_NUDGE_PROMPT
    else:
        nudge_prompt = E2E_NUDGE_PROMPT
    await chat.send_message(nudge_prompt, nudge_prompt)


async def _agent_stream_active(
    chat: McpChatSession,
    *,
    chat_id: str = "",
    api_only: bool = False,
) -> bool:
    if api_only and chat_id.strip():
        tool_activity = await probe_desktop_tool_progress(chat, chat_id=chat_id, api_only=True)
        return bool(tool_activity.get("isStreaming"))
    stream_probe = await chat.probe_desktop_approval_once()
    tool_activity = await probe_desktop_tool_progress(chat, chat_id=chat_id)
    if tool_activity.get("completionStatus") == "complete":
        return False
    if stream_probe.get("isStreaming"):
        return True
    return bool(tool_activity.get("isStreaming"))


async def _fail_if_model_completed_without_desktop_tools(
    chat: McpChatSession,
    *,
    chat_id: str = "",
    api_only: bool = False,
) -> None:
    tool_activity = await probe_desktop_tool_progress(
        chat,
        chat_id=chat_id,
        api_only=api_only,
    )
    if api_only:
        probe: dict[str, object] = {}
    else:
        probe = await chat.probe_desktop_approval_once()
    if probe.get("err") == "model-completed-without-desktop-tools":
        hint = await _provider_readiness_hint()
        raise AssertionError(f"Model finished without desktop tools: {probe}{hint}")
    sample = str(tool_activity.get("assistantSample") or probe.get("lastAssistantSample") or "")
    completion_status = str(tool_activity.get("completionStatus") or "")
    is_streaming = bool(probe.get("isStreaming") or tool_activity.get("isStreaming"))
    if is_streaming and completion_status != "complete" and not sample:
        return
    if tool_activity.get("active") or tool_activity.get("pending"):
        return
    last_tool = str(tool_activity.get("lastTool") or "")
    if last_tool.endswith("desktop_interact_tool"):
        return
    if last_tool.startswith("desktop_"):
        return
    if not sample and completion_status != "complete":
        return
    lowered = sample.lower()
    if "done" in lowered:
        hint = await _provider_readiness_hint()
        raise AssertionError(
            "Model replied DONE without desktop_interact_tool "
            f"(lastTool={last_tool!r}, sample={sample[:120]!r}).{hint}"
        )
    if completion_status == "complete" or sample:
        hint = await _provider_readiness_hint()
        await _abort_stuck_ui_stream(chat)
        raise AssertionError(
            "Model completed assistant turn without calling desktop tools "
            f"(lastTool={last_tool!r}, completion={completion_status!r}, "
            f"assistantSample={sample[:120]!r}).{hint}"
        )


async def wait_for_interact_or_approval(
    chat: McpChatSession,
    *,
    timeout_sec: float = 90.0,
    idle_fail_sec: float = GATE_IDLE_FAIL_FAST_SEC,
    chat_id: str = "",
    api_only: bool = False,
) -> tuple[dict[str, object], str, int, bool]:
    deadline = asyncio.get_event_loop().time() + timeout_sec
    tool_activity: dict[str, object] = {"active": False}
    last_tool = ""
    server_pending = 0
    ui_pending = False
    idle_started: float | None = None
    poll = 0
    api_fail_streak = [0]
    while asyncio.get_event_loop().time() < deadline:
        poll += 1
        heartbeat_e2e_lease()
        tool_activity = await probe_desktop_tool_progress(
            chat,
            chat_id=chat_id,
            api_only=api_only,
        )
        last_tool = str(tool_activity.get("lastTool") or "")
        server_pending = await _resolve_server_pending(api_fail_streak=api_fail_streak)
        ui_pending = bool(tool_activity.get("pending"))
        if _desktop_gate_satisfied(
            last_tool=last_tool,
            server_pending=server_pending,
            ui_pending=ui_pending,
        ):
            return tool_activity, last_tool, server_pending, ui_pending
        if poll % 10 == 0:
            await _fail_if_model_completed_without_desktop_tools(
                chat,
                chat_id=chat_id,
                api_only=api_only,
            )
        if await _agent_stream_active(chat, chat_id=chat_id, api_only=api_only):
            idle_started = None
        elif server_pending >= 0 and not tool_activity.get("active") and not last_tool.startswith("desktop_"):
            now = asyncio.get_event_loop().time()
            if idle_started is None:
                idle_started = now
            elif now - idle_started >= idle_fail_sec:
                hint = await _provider_readiness_hint()
                raise AssertionError(
                    "Model idle without desktop tool activity for "
                    f"{idle_fail_sec:.0f}s (lastTool={last_tool!r}, "
                    f"server_pending={server_pending}, ui_pending={ui_pending})."
                    f"{hint}"
                )
        else:
            idle_started = None
        await asyncio.sleep(1.0)
    return tool_activity, last_tool, server_pending, ui_pending


async def _wait_desktop_tool_activity_failfast(
    chat: McpChatSession,
    *,
    timeout_sec: float,
    idle_fail_sec: float = GATE_IDLE_FAIL_FAST_SEC,
    chat_id: str = "",
    api_only: bool = False,
) -> dict[str, object]:
    deadline = asyncio.get_event_loop().time() + timeout_sec
    last: dict[str, object] = {"active": False}
    idle_started: float | None = None
    streaming_started: float | None = None
    poll = 0
    api_fail_streak = [0]
    while asyncio.get_event_loop().time() < deadline:
        poll += 1
        heartbeat_e2e_lease()
        probe = await probe_desktop_tool_progress(
            chat,
            chat_id=chat_id,
            api_only=api_only,
        )
        if isinstance(probe, dict):
            last = probe
        if poll == 1 or poll % 15 == 0:
            progress(
                f"poll tool activity #{poll} active={last.get('active')} "
                f"pending={last.get('pending')} lastTool={last.get('lastTool')} "
                f"apiLastTool={last.get('apiLastTool')} streaming={last.get('isStreaming')} "
                f"complete={last.get('completionStatus')}"
            )
        if isinstance(probe, dict):
            probe_last_tool = str(probe.get("lastTool") or "")
            if probe.get("pending") or probe_last_tool.startswith("desktop_"):
                if probe_last_tool.endswith("desktop_interact_tool"):
                    return probe
                if probe_last_tool.endswith("desktop_snapshot_tool"):
                    return probe
        server_pending = await _resolve_server_pending(api_fail_streak=api_fail_streak)
        if server_pending > 0:
            return {**last, "pending": True, "serverPending": server_pending}
        now = asyncio.get_event_loop().time()
        if await _agent_stream_active(chat, chat_id=chat_id, api_only=api_only):
            idle_started = None
            if streaming_started is None:
                streaming_started = now
            elif now - streaming_started >= 180.0 and not str(last.get("lastTool") or "").startswith(
                "desktop_"
            ):
                if not api_only:
                    await _abort_stuck_ui_stream(chat)
                raise AssertionError(
                    "Agent stream stuck >180s without desktop tools (aborted for retry)"
                )
        else:
            streaming_started = None
        if poll % 10 == 0:
            await _fail_if_model_completed_without_desktop_tools(
                chat,
                chat_id=chat_id,
                api_only=api_only,
            )
        last_tool = str(last.get("lastTool") or "")
        if await _agent_stream_active(chat, chat_id=chat_id, api_only=api_only):
            idle_started = None
        elif server_pending >= 0 and not last.get("active") and not last_tool.startswith("desktop_"):
            now = asyncio.get_event_loop().time()
            if idle_started is None:
                idle_started = now
            elif now - idle_started >= idle_fail_sec:
                hint = await _provider_readiness_hint()
                raise AssertionError(
                    "Model never started desktop tools within "
                    f"{idle_fail_sec:.0f}s idle window "
                    f"(lastTool={last_tool!r}, server_pending={server_pending})."
                    f"{hint}"
                )
        else:
            idle_started = None
        await asyncio.sleep(1.0)
    hint = await _provider_readiness_hint()
    raise AssertionError(
        f"Desktop tool activity timeout after {timeout_sec:.0f}s: {last}{hint}"
    )


async def ensure_interact_gate(
    chat: McpChatSession,
    *,
    chat_id: str = "",
    textedit_foreground: bool = False,
) -> tuple[dict[str, object], str, int, bool]:
    api_only = textedit_foreground
    tool_activity = await _wait_desktop_tool_activity_failfast(
        chat,
        timeout_sec=APPROVAL_WAIT_SEC,
        chat_id=chat_id,
        api_only=api_only,
    )
    if textedit_foreground:
        progress("agent turn observed via API — activate Chrome for CDP + approval banner")
        await asyncio.to_thread(activate_chrome_foreground)
    progress(
        f"desktop tool activity result active={tool_activity.get('active')} "
        f"pending={tool_activity.get('pending')} lastTool={tool_activity.get('lastTool')} "
        f"err={tool_activity.get('err')}"
    )

    last_tool = str(tool_activity.get("lastTool") or "")
    server_pending = await asyncio.to_thread(server_pending_approval_count)
    ui_pending = bool(tool_activity.get("pending"))

    if not _desktop_gate_satisfied(
        last_tool=last_tool,
        server_pending=server_pending,
        ui_pending=ui_pending,
    ) and last_tool.endswith("desktop_snapshot_tool"):
        progress("snapshot detected — send dref-targeted interact nudge")
        try:
            await _send_interact_nudge(chat, last_tool=last_tool)
        except (RuntimeError, TimeoutError, OSError) as exc:
            raise AssertionError(f"Snapshot nudge send failed (Chrome mux): {exc}") from exc
        heartbeat_e2e_lease()
        tool_activity, last_tool, server_pending, ui_pending = await wait_for_interact_or_approval(
            chat,
            timeout_sec=90.0,
        )

    max_nudge_rounds = 4
    for round_idx in range(max_nudge_rounds):
        if _desktop_gate_satisfied(
            last_tool=last_tool,
            server_pending=server_pending,
            ui_pending=ui_pending,
        ):
            break
        if round_idx == 0 and not (
            last_tool.endswith("desktop_snapshot_tool") or last_tool.endswith("desktop_vision_tool")
        ):
            tool_activity, last_tool, server_pending, ui_pending = await wait_for_interact_or_approval(
                chat,
                timeout_sec=45.0,
            )
            if _desktop_gate_satisfied(
                last_tool=last_tool,
                server_pending=server_pending,
                ui_pending=ui_pending,
            ):
                break
        progress(
            f"nudge model to call desktop_interact_tool "
            f"round {round_idx + 1}/{max_nudge_rounds} lastTool={last_tool!r}"
        )
        try:
            await _send_interact_nudge(chat, last_tool=last_tool)
        except (RuntimeError, TimeoutError, OSError) as exc:
            raise AssertionError(f"Nudge send failed (Chrome mux): {exc}") from exc
        heartbeat_e2e_lease()
        tool_activity, last_tool, server_pending, ui_pending = await wait_for_interact_or_approval(
            chat,
            timeout_sec=90.0,
        )

    provider_hint = await _provider_readiness_hint()
    require_approval_gate_triggered(
        last_tool=last_tool,
        server_pending=server_pending,
        ui_pending=ui_pending,
        provider_hint=provider_hint,
    )
    return tool_activity, last_tool, server_pending, ui_pending
