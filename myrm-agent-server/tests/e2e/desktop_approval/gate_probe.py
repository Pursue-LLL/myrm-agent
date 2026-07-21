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
from tests.e2e.desktop_approval.trust_api import server_pending_approval_count
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


async def probe_desktop_tool_progress(chat: McpChatSession) -> dict[str, object]:
    probe = await chat.evaluate(
        """(() => window.__MYRM_E2E_CHAT__?.getDesktopToolProgress?.() ?? {})()""",
        await_promise=False,
    )
    return probe if isinstance(probe, dict) else {"active": False}


async def _fetch_first_desktop_dref(chat: McpChatSession) -> str | None:
    probe = await chat.evaluate(
        """(() => window.__MYRM_E2E_CHAT__?.getFirstDesktopDref?.() ?? null)()""",
        await_promise=False,
    )
    if probe is None:
        return None
    normalized = str(probe).strip().lstrip("@")
    if normalized.startswith("d") and len(normalized) > 1:
        return normalized
    return None


async def _send_interact_nudge(
    chat: McpChatSession,
    *,
    last_tool: str,
) -> None:
    dref: str | None = None
    if last_tool.endswith("desktop_snapshot_tool"):
        dref = await _fetch_first_desktop_dref(chat)
    if dref:
        progress(f"nudge with concrete dref={dref!r}")
        nudge_prompt = build_desktop_interact_nudge(dref=dref)
    elif last_tool.endswith("desktop_snapshot_tool"):
        nudge_prompt = E2E_SNAPSHOT_NUDGE_PROMPT
    else:
        nudge_prompt = E2E_NUDGE_PROMPT
    await chat.send_message(nudge_prompt, nudge_prompt)


async def _agent_stream_active(chat: McpChatSession) -> bool:
    stream_probe = await chat.probe_desktop_approval_once()
    if stream_probe.get("isStreaming"):
        return True
    tool_activity = await probe_desktop_tool_progress(chat)
    return bool(tool_activity.get("isStreaming"))


async def _fail_if_model_completed_without_desktop_tools(
    chat: McpChatSession,
) -> None:
    probe = await chat.probe_desktop_approval_once()
    if probe.get("err") == "model-completed-without-desktop-tools":
        hint = await _provider_readiness_hint()
        raise AssertionError(f"Model finished without desktop tools: {probe}{hint}")
    sample = str(probe.get("lastAssistantSample") or "")
    if probe.get("isStreaming") or not sample:
        return
    lowered = sample.lower()
    if "desktop" in lowered or "桌面" in sample or "control denied" in lowered or "done" in lowered:
        return
    tool_activity = await probe_desktop_tool_progress(chat)
    if tool_activity.get("active") or tool_activity.get("pending"):
        return
    hint = await _provider_readiness_hint()
    raise AssertionError(
        "Model completed assistant turn without calling desktop tools "
        f"(assistantSample={sample[:120]!r}).{hint}"
    )


async def wait_for_interact_or_approval(
    chat: McpChatSession,
    *,
    timeout_sec: float = 90.0,
    idle_fail_sec: float = GATE_IDLE_FAIL_FAST_SEC,
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
        tool_activity = await probe_desktop_tool_progress(chat)
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
            await _fail_if_model_completed_without_desktop_tools(chat)
        if await _agent_stream_active(chat):
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
) -> dict[str, object]:
    deadline = asyncio.get_event_loop().time() + timeout_sec
    last: dict[str, object] = {"active": False}
    idle_started: float | None = None
    poll = 0
    api_fail_streak = [0]
    while asyncio.get_event_loop().time() < deadline:
        poll += 1
        heartbeat_e2e_lease()
        if poll == 1 or poll % 15 == 0:
            progress(
                f"poll tool activity #{poll} active={last.get('active')} "
                f"pending={last.get('pending')} lastTool={last.get('lastTool')}"
            )
        probe = await probe_desktop_tool_progress(chat)
        if isinstance(probe, dict):
            last = probe
            if probe.get("active") or probe.get("pending"):
                return probe
        server_pending = await _resolve_server_pending(api_fail_streak=api_fail_streak)
        if server_pending > 0:
            return {**last, "pending": True, "serverPending": server_pending}
        if poll % 10 == 0:
            await _fail_if_model_completed_without_desktop_tools(chat)
        last_tool = str(last.get("lastTool") or "")
        if await _agent_stream_active(chat):
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
) -> tuple[dict[str, object], str, int, bool]:
    tool_activity = await _wait_desktop_tool_activity_failfast(
        chat,
        timeout_sec=APPROVAL_WAIT_SEC,
    )
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
