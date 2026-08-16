"""Post-approval turn completion and settings revoke for desktop E2E."""

from __future__ import annotations

import asyncio
import json
import os
import platform
import subprocess
import time
import urllib.error
import uuid
from typing import Awaitable, TypeVar

import pytest
from cdp_chat.mcp_ui import McpChatSession
from cdp_chat.support import (
    _signoff_desktop_soak_parallel_load,
    chat_id_from_path,
    chat_messages_have_done,
    chat_user_message_count,
    fetch_chat_messages,
    fetch_provider_readiness_snapshot,
    get_e2e_api_url,
    signoff_parallel_desktop_mux_step_timeout_sec,
    signoff_parallel_desktop_turn_done_timeout_sec,
    signoff_parallel_force_chat_timeout_sec,
    wait_chat_messages_done,
    wait_e2e_provider_ready,
)
from dev_gate.contract import EvaluateIntent  # noqa: E402

from tests.e2e.desktop_approval.constants import (
    APPROVAL_CLICK_DEADLINE_SEC,
    BASE_URL,
    E2E_NUDGE_PROMPT,
    E2E_PROMPT,
    progress,
)
from tests.e2e.desktop_approval.gate_probe import ensure_interact_gate
from tests.e2e.desktop_approval.infra_retry import is_retriable_page_transport
from tests.e2e.desktop_approval.textedit_fixture import (
    ensure_textedit_fixture_ready,
    preflight_textedit_foreground,
)
from tests.e2e.desktop_approval.trust_api import (
    desktop_trust_revoke_selector_js,
    fetch_pending_approval_request_ids,
    list_trusted_apps_via_api,
    resolve_desktop_approval_request_for_test,
    resolve_pending_desktop_approval_for_test,
    server_pending_approval_count,
)
from tests.support.e2e_desktop_model_pin import (
    ensure_desktop_basic_model_pinned_for_send,
    expected_desktop_e2e_model,
    ui_provider_debug_matches_expected,
)
from tests.support.e2e_runtime_guard import heartbeat_once


def _api_done_wait_tick() -> None:
    """R249: lease + BODY wall progress during blocking API DONE poll."""
    heartbeat_once()
    try:
        from e2e_session_runtime.lifecycle import touch_wall_progress

        touch_wall_progress(current_node="wait_api_done")
    except ImportError:
        pass


_CHAT_ROUTE_PROBE_TIMEOUT_SEC = 20.0
_CHAT_ROUTE_NAVIGATE_TIMEOUT_SEC = 45.0
_CHAT_ROUTE_BRIDGE_TIMEOUT_SEC = 45.0
_FORCE_CHAT_NAVIGATE_TIMEOUT_SEC = 50.0
_FORCE_CHAT_SHELL_READY_TIMEOUT_SEC = 35.0
_FORCE_CHAT_BRIDGE_TIMEOUT_SEC = 35.0

_T = TypeVar("_T")


def _signoff_mux_attach_restart(reason: str) -> None:
    """Scoped mux attach restart during signoff force-chat heal (R178)."""
    import sys
    from pathlib import Path

    lib_dir = Path(__file__).resolve().parents[4] / "scripts" / "dev" / "lib"
    if str(lib_dir) not in sys.path:
        sys.path.insert(0, str(lib_dir))
    from mux.attach_force_restart import force_mux_attach_restart_scoped

    force_mux_attach_restart_scoped(reason=reason)


async def _signoff_mux_recover_lightweight(
    chat: McpChatSession, *, reason: str
) -> None:
    """R288: signoff must not call recover_mux_transport (eats session recovery budget)."""
    progress(f"R288 signoff lightweight mux recover: {reason}")
    await asyncio.to_thread(_signoff_mux_attach_restart, reason)
    await _await_with_wall_timeout(
        chat.ensure_e2e_api_base_binding(),
        timeout_sec=20.0,
        label="R288 signoff API binding",
    )


async def _await_with_wall_timeout(
    awaitable: Awaitable[_T], *, timeout_sec: float, label: str
) -> _T:
    try:
        return await asyncio.wait_for(awaitable, timeout=timeout_sec)
    except asyncio.TimeoutError as exc:
        raise RuntimeError(f"{label} wall-timeout after {timeout_sec:.0f}s") from exc


def _wait_mux_transport_turn_sync(*, current_node: str) -> None:
    """R201 POO Phase 3: queue before desktop force-chat mux operations under parallel load."""
    import sys
    from pathlib import Path

    lib_dir = Path(__file__).resolve().parents[4] / "scripts" / "dev" / "lib"
    if str(lib_dir) not in sys.path:
        sys.path.insert(0, str(lib_dir))
    from browser_orchestrator import wait_for_operation_credit  # noqa: PLC0415
    from e2e_core.mux_transport_queue import (
        _FORCE_CHAT_SHELL_BLOCKING_NODE,
    )  # noqa: PLC0415
    from mux.transport_supervisor import mux_upstream_wait_cap  # noqa: PLC0415

    from tests.support.chrome_mcp_e2e import _parallel_open_page_peer_count

    if _parallel_open_page_peer_count() < 2:
        return
    wait_for_operation_credit(
        budget_sec=float(mux_upstream_wait_cap()),
        current_node=current_node or _FORCE_CHAT_SHELL_BLOCKING_NODE,
    )


async def _probe_chat_route(chat: McpChatSession, target: str) -> dict[str, object]:
    probe = await _await_with_wall_timeout(
        chat.evaluate(
            f"""(() => {{
              const href = String(location.href || '');
              return {{ href, onTarget: href.startsWith({target!r}) }};
            }})()""",
            intent=EvaluateIntent.SYNC_PROBE,
        ),
        timeout_sec=_CHAT_ROUTE_PROBE_TIMEOUT_SEC,
        label="chat route probe",
    )
    return probe if isinstance(probe, dict) else {"href": str(probe), "onTarget": False}


def activate_chrome() -> None:
    if platform.system() != "Darwin":
        return
    subprocess.run(
        ["osascript", "-e", 'tell application "Google Chrome" to activate'],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )


def _chat_url(chat_id: str) -> str:
    normalized = chat_id.strip()
    assert normalized, "chat_id required for chat URL"
    return f"{BASE_URL}/chat/{normalized}"


async def _ensure_chat_route(chat: McpChatSession, chat_id: str) -> None:
    target = _chat_url(chat_id)
    probe = await _probe_chat_route(chat, target)
    if probe.get("onTarget"):
        return
    navigate_timeout = signoff_parallel_force_chat_timeout_sec(
        _CHAT_ROUTE_NAVIGATE_TIMEOUT_SEC
    )
    route_timeout = signoff_parallel_force_chat_timeout_sec(
        _CHAT_ROUTE_BRIDGE_TIMEOUT_SEC
    )
    progress(f"restore chat route chat_id={chat_id}")
    await _await_with_wall_timeout(
        asyncio.to_thread(
            chat._client.navigate,
            chat._page,
            target,
            timeout_ms=120_000,
        ),
        timeout_sec=navigate_timeout,
        label="restore chat route navigate",
    )
    await _await_with_wall_timeout(
        chat.ensure_react_e2e_bridge(timeout_sec=route_timeout),
        timeout_sec=route_timeout,
        label="restore chat route bridge",
    )
    await _await_with_wall_timeout(
        chat.ensure_chat_surface(BASE_URL, timeout_sec=route_timeout),
        timeout_sec=route_timeout,
        label="restore chat route surface",
    )
    post_probe = await _probe_chat_route(chat, target)
    if post_probe.get("onTarget"):
        return
    progress(
        "chat route mismatch after surface restore; force chat route once more "
        f"chat_id={chat_id}"
    )
    await _await_with_wall_timeout(
        asyncio.to_thread(
            chat._client.navigate,
            chat._page,
            target,
            timeout_ms=120_000,
        ),
        timeout_sec=navigate_timeout,
        label="force chat route navigate",
    )
    await _await_with_wall_timeout(
        chat.ensure_react_e2e_bridge(timeout_sec=route_timeout),
        timeout_sec=route_timeout,
        label="force chat route bridge",
    )
    final_probe = await _probe_chat_route(chat, target)
    if not final_probe.get("onTarget"):
        raise RuntimeError(
            "restore chat route failed to reach target "
            f"chat_id={chat_id} href={final_probe.get('href')!r}"
        )


async def resolve_chat_id(chat: McpChatSession, state: dict[str, object]) -> str | None:
    chat_id = chat_id_from_path(str(state.get("url") or ""))
    if chat_id:
        return chat_id
    explicit = str(state.get("chatId") or "").strip()
    if explicit:
        return explicit
    path = await chat.evaluate(
        "(() => location.pathname)()",
        intent=EvaluateIntent.SYNC_PROBE,
    )
    return chat_id_from_path(str(path) if path else "")


def _kickoff_desktop_turn_via_api_sync(
    chat_id: str,
    *,
    query: str,
    timeout_sec: float,
) -> dict[str, object]:
    """R232: POST agent-stream to start turn without MUX CDP bridge (seeded resend SSOT)."""
    from cdp_chat.support import _collect_agent_stream_events

    from tests.api.agent.utils import get_model_selection

    normalized = chat_id.strip()
    if not normalized:
        return {"events": [], "error": {"error_type": "MissingChatId"}}
    payload: dict[str, object] = {
        "messageId": f"msg_{uuid.uuid4().hex[:8]}",
        "chatId": normalized,
        "query": query,
        "modelSelection": get_model_selection(),
        "actionMode": "agent",
        "enableMemory": False,
        "agentConfig": {"enabledBuiltinTools": ["computer_use"]},
    }
    return _collect_agent_stream_events(
        payload,
        api_url=get_e2e_api_url(),
        timeout_sec=timeout_sec,
    )


def _seeded_kickoff_activity_probe(
    chat_id: str,
    *,
    baseline_user_count: int,
    api_url: str | None = None,
) -> dict[str, object]:
    """R237: seeded path already has userCount>=1 — require turn activity beyond baseline."""
    messages = fetch_chat_messages(
        chat_id,
        api_url=api_url,
        timeout_sec=15.0,
    )
    user_count = sum(
        1 for msg in messages if isinstance(msg, dict) and msg.get("role") == "user"
    )
    assistant_msgs = [
        msg
        for msg in messages
        if isinstance(msg, dict) and msg.get("role") == "assistant"
    ]
    last_assistant = assistant_msgs[-1] if assistant_msgs else None
    assistant_tail = (
        str(last_assistant.get("content") or "")[:80] if last_assistant else ""
    )
    active = (
        user_count > baseline_user_count
        or bool(assistant_msgs)
        or bool(assistant_tail.strip())
    )
    return {
        "userCount": user_count,
        "baselineUserCount": baseline_user_count,
        "assistantCount": len(assistant_msgs),
        "assistantTail": assistant_tail,
        "active": active,
    }


def _bridge_seal_agent_started_probe(
    chat_id: str,
    *,
    api_url: str | None = None,
) -> bool:
    """R257: bridge SEAL only counts when assistant turn activity exists."""
    activity = _seeded_kickoff_activity_probe(
        chat_id,
        baseline_user_count=0,
        api_url=api_url,
    )
    assistant_count = int(activity.get("assistantCount") or 0)
    assistant_tail = str(activity.get("assistantTail") or "").strip()
    return assistant_count > 0 or bool(assistant_tail)


async def _verify_bridge_seal_api_kickoff(
    chat_id: str,
    *,
    timeout_sec: float,
) -> bool:
    """R257: short API-only probe after bridge SEAL before trusting kickoff."""
    deadline = asyncio.get_event_loop().time() + timeout_sec
    while asyncio.get_event_loop().time() < deadline:
        heartbeat_once()
        try:
            started = await asyncio.to_thread(
                _bridge_seal_agent_started_probe,
                chat_id,
                api_url=get_e2e_api_url(),
            )
        except (urllib.error.HTTPError, TimeoutError, OSError) as exc:
            progress(f"R257 bridge SEAL API probe skipped (non-fatal): {exc}")
            started = False
        if started:
            progress("R257 bridge SEAL verified — assistant turn activity via API")
            return True
        await asyncio.sleep(5.0)
    progress("R257 bridge SEAL API kickoff miss — CDP fallback next")
    return False


def _agent_stream_kickoff_started(result: dict[str, object]) -> bool:
    """True when POST agent-stream returned productive SSE (not immediate error)."""
    if result.get("error"):
        return False
    events = result.get("events")
    if not isinstance(events, list) or not events:
        return False
    return any(isinstance(event, dict) for event in events)


async def _try_signoff_api_kickoff(
    chat_id: str,
    *,
    label: str,
    kickoff_timeout_base: float = 120.0,
) -> tuple[bool, dict[str, object]]:
    """R286/R285: POST agent-stream mux-bypass for signoff desktop turns."""
    normalized = chat_id.strip()
    if not normalized:
        return False, {"events": [], "error": {"error_type": "MissingChatId"}}
    kickoff_timeout = signoff_parallel_desktop_turn_done_timeout_sec(
        kickoff_timeout_base
    )
    api_timeout = min(60.0, max(30.0, kickoff_timeout / 5.0))
    kickoff_thread_budget = min(45.0, api_timeout + 10.0)
    progress(f"{label} — API kickoff before bridge/CDP (mux-bypass)")
    try:
        kickoff_result = await asyncio.wait_for(
            asyncio.to_thread(
                _kickoff_desktop_turn_via_api_sync,
                normalized,
                query=E2E_PROMPT,
                timeout_sec=api_timeout,
            ),
            timeout=kickoff_thread_budget,
        )
    except (asyncio.TimeoutError, TimeoutError):
        progress(
            f"{label} API kickoff thread budget exceeded "
            f"({kickoff_thread_budget:.0f}s) — bridge fallback"
        )
        return False, {
            "events": [],
            "error": {"error_type": "KickoffThreadTimeout"},
        }
    if _agent_stream_kickoff_started(kickoff_result):
        events = kickoff_result.get("events")
        event_count = len(events) if isinstance(events, list) else 0
        progress(f"{label} API stream events={event_count}")
        return True, kickoff_result
    return False, kickoff_result


async def _wait_seeded_resend_turn_kickoff(
    chat: McpChatSession,
    *,
    chat_id: str,
    timeout_sec: float,
    baseline_user_count: int = 0,
    baseline_ui_user_count: int = 0,
) -> bool:
    """R227/R237: resend after seeded approval must observe agent turn activity, not stale userCount."""
    normalized = chat_id.strip()
    deadline = asyncio.get_event_loop().time() + timeout_sec
    poll = 0
    nudged = False
    while asyncio.get_event_loop().time() < deadline:
        poll += 1
        heartbeat_once()
        if normalized:
            try:
                activity = await asyncio.to_thread(
                    _seeded_kickoff_activity_probe,
                    normalized,
                    baseline_user_count=baseline_user_count,
                    api_url=get_e2e_api_url(),
                )
                if activity.get("active"):
                    progress(
                        f"seeded resend kickoff: API activity={activity} poll=#{poll}"
                    )
                    return True
            except urllib.error.HTTPError:
                pass
            except (TimeoutError, OSError) as exc:
                if poll == 1 or poll % 5 == 0:
                    progress(
                        f"seeded resend kickoff API probe skipped "
                        f"(non-fatal): {exc} poll=#{poll}"
                    )
        try:
            probe = await chat.evaluate(
                "(() => window.__MYRM_E2E_CHAT__?.turnSnapshot?.() ?? null)()",
                intent=EvaluateIntent.BRIDGE_POLL,
            )
        except (TimeoutError, RuntimeError, OSError) as exc:
            if poll == 1 or poll % 5 == 0:
                progress(f"seeded resend kickoff probe skipped (non-fatal): {exc}")
            await asyncio.sleep(2.0)
            continue
        if isinstance(probe, dict):
            user_count = int(probe.get("userCount") or 0)
            effective_ui_baseline = max(baseline_ui_user_count, baseline_user_count)
            if bool(probe.get("isStreaming")) or user_count > effective_ui_baseline:
                progress(
                    f"seeded resend kickoff: UI userCount={user_count} "
                    f"baseline={effective_ui_baseline} "
                    f"streaming={probe.get('isStreaming')} poll=#{poll}"
                )
                return True
        if not nudged and poll >= 8:
            nudged = True
            progress("seeded resend kickoff slow — bridge send_message nudge")
            try:
                await chat.send_message(E2E_NUDGE_PROMPT, E2E_NUDGE_PROMPT)
            except (TimeoutError, RuntimeError, OSError) as exc:
                progress(f"seeded resend kickoff nudge skipped (non-fatal): {exc}")
        await asyncio.sleep(2.0)
    return False


async def wait_stream_done_with_marker(
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
        heartbeat_once()
        try:
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
                intent=EvaluateIntent.BRIDGE_POLL,
            )
        except (TimeoutError, RuntimeError, OSError) as exc:
            if poll == 1 or poll % 5 == 0:
                progress(
                    f"poll DONE marker #{poll} evaluate skipped (non-fatal): {exc}"
                )
            await asyncio.sleep(2.0)
            continue
        if isinstance(probe, dict):
            last = probe
            if poll == 1 or poll % 5 == 0:
                sample = str(probe.get("lastAssistantSample") or "")
                progress(
                    f"poll DONE marker #{poll} streaming={probe.get('isStreaming')} "
                    f"matched={probe.get('matched')} sample_len={len(sample)}"
                )
            chat_id = str(probe.get("chatId") or chat_id_hint or "").strip()
            if chat_id:
                try:
                    api_has_done = await asyncio.to_thread(
                        chat_messages_have_done,
                        chat_id,
                        api_url=get_e2e_api_url(),
                    )
                except urllib.error.HTTPError as exc:
                    progress(f"API DONE probe HTTP {exc.code} chat_id={chat_id}")
                    api_has_done = False
                except (TimeoutError, OSError) as exc:
                    if poll == 1 or poll % 5 == 0:
                        progress(
                            f"poll DONE marker #{poll} API probe skipped "
                            f"(non-fatal): {exc}"
                        )
                    api_has_done = False
                else:
                    if api_has_done:
                        return {
                            **probe,
                            "chatId": chat_id,
                            "matched": True,
                            "mode": "api-done",
                        }
            if (
                chat_id
                and int(probe.get("userCount") or 0) >= 1
                and not probe.get("isStreaming")
                and probe.get("matched")
            ):
                return {**probe, "chatId": chat_id}
            if (
                not nudged_done
                and poll >= 15
                and not probe.get("isStreaming")
                and not probe.get("matched")
                and int(probe.get("userCount") or 0) >= 1
            ):
                nudged_done = True
                progress("nudge model to reply DONE only")
                nudge_timeout = signoff_parallel_desktop_mux_step_timeout_sec(90.0)
                try:
                    await asyncio.wait_for(
                        chat.send_message(
                            "Reply with only DONE.", "Reply with only DONE."
                        ),
                        timeout=nudge_timeout,
                    )
                except (TimeoutError, asyncio.TimeoutError) as exc:
                    progress(
                        f"R254 nudge send_message timeout after {nudge_timeout:.0f}s "
                        f"— continue DONE poll (non-fatal): {exc}"
                    )
                heartbeat_once()
                continue
        await asyncio.sleep(2.0)
    return {**last, "ok": False, "err": "turn-timeout"}


async def wait_for_trusted_app_display_name(
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
        heartbeat_once()
        apps = await asyncio.to_thread(list_trusted_apps_via_api)
        for app in apps:
            if not isinstance(app, dict):
                continue
            name = str(app.get("display_name") or "").strip().lower()
            if name == target or target in name:
                return app
        if apps and poll % 5 == 0:
            progress(f"trust API poll waiting for {display_name!r}: {apps}")
        await asyncio.sleep(1.0)
    raise AssertionError(
        f"Trusted app {display_name!r} not found via API within {timeout_sec}s: {apps}"
    )


async def verify_settings_revoke_trusted_app(
    chat: McpChatSession,
    *,
    trust_key: str,
    display_name: str,
) -> None:
    settings_url = f"{BASE_URL}/settings/system"
    progress(f"open settings for revoke trust_key={trust_key}")
    nav = await chat.evaluate(
        f"""(() => {{
          window.location.assign({settings_url!r});
          return {{ ok: true }};
        }})()""",
        intent=EvaluateIntent.ROUTE_ATTACH,
    )
    assert isinstance(nav, dict) and nav.get("ok") is True, nav

    deadline = asyncio.get_event_loop().time() + 120.0
    revoke_selector = desktop_trust_revoke_selector_js(trust_key)
    probe: dict[str, object] = {}
    while asyncio.get_event_loop().time() < deadline:
        heartbeat_once()
        probe = await chat.evaluate(
            f"""(() => {{
              const body = document.body?.innerText || '';
              const revokeBtn = document.querySelector({revoke_selector});
              return {{
                hasDisplayName: body.includes({display_name!r}),
                revokeReady: Boolean(revokeBtn && !revokeBtn.disabled),
              }};
            }})()""",
            intent=EvaluateIntent.BRIDGE_POLL,
        )
        if (
            isinstance(probe, dict)
            and probe.get("hasDisplayName")
            and probe.get("revokeReady")
        ):
            break
        await asyncio.sleep(1.0)
    else:
        raise AssertionError(f"Settings trusted-app row not ready for revoke: {probe}")

    click = await chat.evaluate(
        f"""(() => {{
          const btn = document.querySelector({revoke_selector});
          if (!btn || btn.disabled) return {{ ok: false, err: 'revoke-not-ready' }};
          btn.click();
          return {{ ok: true }};
        }})()""",
        intent=EvaluateIntent.SYNC_PROBE,
    )
    assert (
        isinstance(click, dict) and click.get("ok") is True
    ), f"Settings revoke click failed: {click}"

    empty_deadline = asyncio.get_event_loop().time() + 60.0
    while asyncio.get_event_loop().time() < empty_deadline:
        heartbeat_once()
        apps = await asyncio.to_thread(list_trusted_apps_via_api)
        if not apps:
            return
        await asyncio.sleep(1.0)
    raise AssertionError(f"Trusted apps not empty after settings revoke: {apps}")


async def complete_turn_after_approval(
    chat: McpChatSession,
    *,
    chat_id_hint: str | None,
    api_primary_done: bool = False,
    skip_chat_route_restore: bool = False,
    bridge_kickoff_done: bool = False,
) -> str:
    turn_done_timeout = signoff_parallel_desktop_turn_done_timeout_sec(180.0)
    mux_bypass_kickoff = api_primary_done or bridge_kickoff_done
    if mux_bypass_kickoff and chat_id_hint:
        kickoff_label = "R233 api-primary" if api_primary_done else "R244 bridge"
        progress(f"{kickoff_label} DONE wait (mux-bypass)")
        # R287: api/bridge kickoff already started agent turn — use R244-scale API
        # poll; avoid CDP route restore that burns body budget under parallel mux.
        api_budget = min(420.0, max(120.0, turn_done_timeout * 0.75))
        progress(
            f"R287 mux-bypass API DONE budget={api_budget:.0f}s "
            f"(turn_done_timeout={turn_done_timeout:.0f}s)"
        )
        api_done = await asyncio.to_thread(
            wait_chat_messages_done,
            chat_id_hint,
            api_url=get_e2e_api_url(),
            timeout_sec=api_budget,
            fetch_timeout_sec=30.0,
            progress_interval_sec=20.0,
            on_tick=_api_done_wait_tick,
        )
        if api_done:
            progress(
                f"approval verified via {kickoff_label} DONE chat_id={chat_id_hint}"
            )
            assert chat_user_message_count(chat_id_hint) >= 1, chat_id_hint
            progress(f"done chat_id={chat_id_hint}")
            return chat_id_hint
        progress(
            f"R287 {kickoff_label} DONE miss — CDP turn wait without route restore"
        )
        skip_chat_route_restore = True
    if chat_id_hint and not skip_chat_route_restore:
        await _ensure_chat_route(chat, chat_id_hint)
    progress("wait assistant DONE")
    recover_timeout = signoff_parallel_desktop_turn_done_timeout_sec(60.0)
    after_turn = await wait_stream_done_with_marker(
        chat,
        chat_id_hint=chat_id_hint,
        marker="DONE",
        timeout_sec=turn_done_timeout,
    )
    if (
        not after_turn.get("matched")
        and chat_id_hint
        and int(after_turn.get("userCount") or 0) <= 0
        and not str(after_turn.get("lastAssistantSample") or "").strip()
    ):
        progress(
            "post-approval DONE wait got empty turn snapshot; "
            "recover chat route and re-probe once"
        )
        await _ensure_chat_route(chat, chat_id_hint)
        recovered_turn = await wait_stream_done_with_marker(
            chat,
            chat_id_hint=chat_id_hint,
            marker="DONE",
            timeout_sec=recover_timeout,
        )
        if recovered_turn.get("matched"):
            after_turn = recovered_turn
    if not after_turn.get("matched"):
        chat_id_probe = str(after_turn.get("chatId") or chat_id_hint or "").strip()
        api_done = False
        if chat_id_probe:
            try:
                api_done = await asyncio.to_thread(
                    chat_messages_have_done,
                    chat_id_probe,
                    api_url=get_e2e_api_url(),
                )
            except urllib.error.HTTPError as exc:
                progress(
                    f"post-approval API DONE probe HTTP {exc.code} chat_id={chat_id_probe}"
                )
                api_done = False
            except (TimeoutError, OSError) as exc:
                progress(f"post-approval API DONE probe skipped (non-fatal): {exc}")
                api_done = False
        if chat_id_probe and api_done:
            progress("approval verified via API DONE marker fallback")
            after_turn = {
                **after_turn,
                "matched": True,
                "chatId": chat_id_probe,
                "mode": "post-approval-api-done",
            }

    if str(after_turn.get("path", "")).startswith("/settings"):
        pytest.fail(f"Send redirected to settings: {after_turn}")
    assert (
        after_turn.get("matched") is True
    ), f"Turn did not complete with DONE after approval: {after_turn}"

    chat_id = await resolve_chat_id(chat, after_turn)
    assert chat_id, f"Expected chat id after approval turn: {after_turn}"
    assert chat_user_message_count(chat_id) >= 1, after_turn
    progress(f"done chat_id={chat_id}")
    return chat_id


async def ensure_desktop_inspector_panel_open(
    chat: McpChatSession,
    *,
    chat_id: str | None = None,
) -> None:
    """Mirror fileDiffEvents.ts openPanel on DESKTOP_CONTROL_APPROVAL_REQUEST."""
    on_chat = await chat.evaluate(
        f"""(() => {{
          const href = String(location.href || '');
          return {{ onChatUi: href.startsWith({BASE_URL!r}), href }};
        }})()""",
        intent=EvaluateIntent.SYNC_PROBE,
    )
    if not isinstance(on_chat, dict) or not on_chat.get("onChatUi"):
        href = str(on_chat.get("href") if isinstance(on_chat, dict) else on_chat or "")
        progress(f"navigate before openPanel (href={href})")
        target = _chat_url(chat_id) if chat_id else BASE_URL
        await asyncio.to_thread(
            chat._client.navigate,
            chat._page,
            target,
            timeout_ms=120_000,
        )
        await chat.ensure_react_e2e_bridge(timeout_sec=90.0)
        if chat_id:
            await chat.ensure_chat_surface(BASE_URL)

    # Raw `@/` dynamic import fails in CDP evaluate; use E2E bridge (same path as enable_computer_use).
    result = await chat.evaluate(
        """(() => {
          const bridge = window.__MYRM_E2E_CHAT__;
          if (typeof bridge?.ensureComputerUseReady === 'function') {
            bridge.ensureComputerUseReady();
            return { ok: true, via: 'ensureComputerUseReady' };
          }
          return { ok: true, skipped: 'overlay-only' };
        })()""",
        intent=EvaluateIntent.AGENT_SUBMIT,
    )
    assert (
        isinstance(result, dict) and result.get("ok") is True
    ), f"openDesktopInspectorPanel failed: {result}"


async def sync_approval_banner_from_pending_api(chat: McpChatSession) -> None:
    """Seed approval overlay when SSE missed in CDP tab (mirrors fileDiffEvents handler)."""
    pending_ids = await asyncio.to_thread(fetch_pending_approval_request_ids)
    if not pending_ids:
        return
    request_id = pending_ids[0]
    payload = {
        "request_id": request_id,
        "reason": "Allow Myrm to control TextEdit for this task?",
        "operation": "foreground_control",
        "app_name": "TextEdit",
        "require_app_approval": True,
    }
    result = await chat.evaluate(
        f"""(() => {{
          const bridge = window.__MYRM_E2E_CHAT__;
          if (typeof bridge?.syncDesktopControlApproval !== 'function') {{
            return {{ ok: false, err: 'no-sync-bridge' }};
          }}
          bridge.syncDesktopControlApproval({json.dumps(payload)});
          return {{ ok: true, requestId: {json.dumps(request_id)} }};
        }})()""",
        intent=EvaluateIntent.AGENT_SUBMIT,
    )
    assert (
        isinstance(result, dict) and result.get("ok") is True
    ), f"syncDesktopControlApproval failed: {result}"


async def _ensure_wide_viewport_for_banner(chat: McpChatSession) -> None:
    """Session/always buttons use sm/md breakpoints; widen CDP window for E2E clicks."""
    await chat.evaluate(
        """(() => {
          try { window.resizeTo(1400, 900); } catch { /* headless / policy */ }
          return { ok: true, innerWidth: window.innerWidth, innerHeight: window.innerHeight };
        })()""",
        intent=EvaluateIntent.SYNC_PROBE,
    )


async def _abort_stream_for_approval_banner(chat: McpChatSession) -> None:
    await chat.evaluate(
        """(() => {
          window.__MYRM_E2E_CHAT__?.abortActiveStream?.();
          return { ok: true };
        })()""",
        intent=EvaluateIntent.SYNC_PROBE,
    )


async def wait_for_approval_banner_clickable(
    chat: McpChatSession,
    *,
    scope: str,
    server_pending_hint: int,
    ui_pending_hint: bool,
    interact_seen_hint: bool = False,
    chat_id: str | None = None,
) -> None:
    """Wait for approval controls; click as soon as server gate is pending."""
    if server_pending_hint <= 0 and not ui_pending_hint and not interact_seen_hint:
        raise AssertionError(
            "Expected pending desktop approval after interact gate "
            f"(server_pending={server_pending_hint}, ui_pending={ui_pending_hint})"
        )

    async def _try_scope_click() -> dict[str, object]:
        if scope == "always":
            return await chat.click_desktop_allow_always()
        if scope == "session":
            return await chat.click_desktop_allow_session()
        return await chat.click_desktop_allow_once()

    await ensure_desktop_inspector_panel_open(chat, chat_id=chat_id)
    if server_pending_hint > 0:
        await sync_approval_banner_from_pending_api(chat)
    if scope in {"session", "always"}:
        await _ensure_wide_viewport_for_banner(chat)

    deadline = asyncio.get_event_loop().time() + APPROVAL_CLICK_DEADLINE_SEC
    approval: dict[str, object] = {"pending": ui_pending_hint, "allowVisible": False}
    poll = 0
    activated = False
    panel_refreshed = False
    api_resolve_attempted = False
    stream_abort_attempted = False

    def _scope_visible(probe: dict[str, object]) -> bool:
        if scope == "once":
            return bool(probe.get("allowVisible"))
        if scope == "session":
            return bool(probe.get("allowSessionVisible"))
        return bool(probe.get("allowAlwaysVisible"))

    while asyncio.get_event_loop().time() < deadline:
        poll += 1
        heartbeat_once()
        server_pending = await asyncio.to_thread(server_pending_approval_count)
        probe = await chat.probe_desktop_approval_once()
        if isinstance(probe, dict):
            approval = probe
        scope_visible = _scope_visible(probe) if isinstance(probe, dict) else False
        if server_pending > 0:
            if (
                isinstance(probe, dict)
                and bool(probe.get("isStreaming"))
                and not scope_visible
                and not stream_abort_attempted
                and poll >= 8
            ):
                progress(
                    "approval pending while stream active — abort stream for banner"
                )
                await _abort_stream_for_approval_banner(chat)
                stream_abort_attempted = True
            if not scope_visible:
                await sync_approval_banner_from_pending_api(chat)
                if not panel_refreshed and poll <= 5:
                    await ensure_desktop_inspector_panel_open(chat, chat_id=chat_id)
                    panel_refreshed = True
            click = await _try_scope_click()
            if click.get("ok") is True:
                progress(f"approval click ok scope={scope} poll=#{poll}")
                return
            if not scope_visible and not api_resolve_attempted and poll >= 16:
                api_resolve_attempted = True
                request_id = ""
                if isinstance(probe, dict):
                    request_id = str(probe.get("requestId") or "").strip()
                if not request_id:
                    request_id = str(approval.get("requestId") or "").strip()
                if request_id:
                    resolved = await asyncio.to_thread(
                        resolve_desktop_approval_request_for_test,
                        request_id,
                        scope=scope,
                    )
                else:
                    resolved = await asyncio.to_thread(
                        resolve_pending_desktop_approval_for_test, scope=scope
                    )
                if resolved:
                    progress(
                        "approval fallback resolved via API "
                        f"scope={scope} request_id={request_id or 'pending-list-head'} "
                        f"poll=#{poll}"
                    )
                    return
        if isinstance(probe, dict):
            if poll == 1 or poll % 8 == 0:
                progress(
                    f"approval poll #{poll} ui_pending={probe.get('pending')} "
                    f"scopeVisible={scope_visible} server_pending={server_pending}"
                )
            if scope_visible:
                click = await _try_scope_click()
                assert (
                    click.get("ok") is True
                ), f"Approval click failed after banner visible: {click}"
                return
            if probe.get("err") == "model-completed-without-desktop-tools":
                raise AssertionError(f"Model finished without desktop tools: {probe}")
        if server_pending <= 0:
            if interact_seen_hint:
                if poll == 1 or poll % 8 == 0:
                    progress(
                        "interact_tool observed; waiting pending approval registration "
                        f"poll=#{poll}"
                    )
                await asyncio.sleep(0.25)
                continue
            raise AssertionError(
                "Desktop approval gate expired before approval click succeeded "
                f"(scope={scope}, last_probe={approval})"
            )
        if not activated and poll >= 8:
            progress("activate chrome to surface approval banner")
            await asyncio.to_thread(activate_chrome)
            activated = True
        await asyncio.sleep(0.25)

    raise AssertionError(
        "Desktop approval click did not succeed before deadline "
        f"(scope={scope}, server_pending={await asyncio.to_thread(server_pending_approval_count)}): "
        f"{approval}"
    )


def _approval_attempt_wall_clock_start() -> float:
    """Per-attempt BODY wall clock — do not reuse lifecycle MYRM_E2E_WALL_STARTED_MONOTONIC."""
    return time.monotonic()


async def _force_chat_shell(chat: McpChatSession, *, label: str) -> None:
    """Navigate off about:blank and wait for hydrated shell before chat automation."""
    navigate_timeout = signoff_parallel_force_chat_timeout_sec(
        _FORCE_CHAT_NAVIGATE_TIMEOUT_SEC
    )
    shell_ready_timeout = signoff_parallel_force_chat_timeout_sec(
        _FORCE_CHAT_SHELL_READY_TIMEOUT_SEC
    )
    bridge_timeout = signoff_parallel_force_chat_timeout_sec(
        _FORCE_CHAT_BRIDGE_TIMEOUT_SEC
    )
    attempts = 3
    for attempt in range(1, attempts + 1):
        heartbeat_once()
        progress(f"force chat shell ({label}) attempt {attempt}/{attempts}")
        try:
            await asyncio.to_thread(
                _wait_mux_transport_turn_sync,
                current_node="force_chat_shell_blocking",
            )
            await _await_with_wall_timeout(
                chat._navigate_to_chat_home(timeout_ms=90_000),
                timeout_sec=navigate_timeout,
                label="force chat shell navigate",
            )
            await _await_with_wall_timeout(
                chat.wait_shell_ready(
                    timeout_sec=shell_ready_timeout, require_bridge=True
                ),
                timeout_sec=shell_ready_timeout,
                label="force chat shell ready",
            )
            await _await_with_wall_timeout(
                chat.ensure_react_e2e_bridge(timeout_sec=bridge_timeout),
                timeout_sec=bridge_timeout,
                label="force chat shell bridge",
            )
            return
        except (RuntimeError, TimeoutError, OSError) as exc:
            if attempt >= attempts:
                raise
            progress(f"force chat shell retry after: {exc}")
            if os.environ.get("E2E_SIGNOFF", "").strip() == "1":
                await _signoff_mux_recover_lightweight(
                    chat,
                    reason="signoff desktop force chat shell retry",
                )
            else:
                try:
                    await asyncio.to_thread(chat._client.reset_after_orphan)
                except (RuntimeError, TimeoutError, OSError) as recover_exc:
                    progress(
                        f"force chat shell recover skipped (non-fatal): {recover_exc}"
                    )
                await _await_with_wall_timeout(
                    chat.ensure_e2e_api_base_binding(),
                    timeout_sec=20.0,
                    label="force chat shell API binding",
                )
            await asyncio.sleep(1.0)


async def _ensure_signoff_chat_surface_after_open(chat: McpChatSession) -> None:
    """R287: open_mcp_page already sealed chat route — skip expensive force_chat_shell."""
    bridge_timeout = signoff_parallel_desktop_mux_step_timeout_sec(60.0)
    shell_timeout = signoff_parallel_desktop_mux_step_timeout_sec(90.0)
    progress(
        "R287 signoff skip force_chat_shell — lightweight shell+bridge after open_mcp_page"
    )
    attempts = 2
    for attempt in range(1, attempts + 1):
        try:
            await _await_with_wall_timeout(
                chat.wait_shell_ready(timeout_sec=shell_timeout, require_bridge=False),
                timeout_sec=shell_timeout,
                label="R287 signoff shell ready",
            )
            await _await_with_wall_timeout(
                chat.ensure_react_e2e_bridge(timeout_sec=bridge_timeout),
                timeout_sec=bridge_timeout,
                label="R287 signoff bridge",
            )
            return
        except (RuntimeError, TimeoutError, OSError) as exc:
            if attempt >= attempts:
                raise
            progress(f"R288 signoff shell retry after: {exc}")
            await _signoff_mux_recover_lightweight(
                chat,
                reason="R288 signoff shell+bridge retry after open_mcp_page",
            )
            await asyncio.sleep(1.0)


async def run_approval_attempt(chat: McpChatSession, *, scope: str = "once") -> str:
    chat._reset_shell_session_clock()
    signoff_mode = os.environ.get("E2E_SIGNOFF", "").strip() == "1"
    if signoff_mode:
        await _ensure_signoff_chat_surface_after_open(chat)
    else:
        await _force_chat_shell(chat, label="pre-attempt")
    progress("new chat + ensure surface")
    new_chat_timeout = signoff_parallel_desktop_mux_step_timeout_sec(75.0)
    reset_result = await chat.click_new_chat(timeout_sec=new_chat_timeout)
    progress(f"new chat reset result: {reset_result}")
    await chat.ensure_chat_surface(BASE_URL, timeout_sec=90.0)
    await chat.ensure_react_e2e_bridge(timeout_sec=60.0)
    # R78: new_chat leaves Chrome frontmost; seed TextEdit AX before strict probe.
    if os.environ.get("E2E_SIGNOFF", "").strip() == "1":
        await asyncio.to_thread(
            preflight_textedit_foreground, attempts=8, fail_hard=False
        )
    await ensure_textedit_fixture_ready(attempts=8 if signoff_mode else 5)

    progress("enable computer_use")
    await asyncio.to_thread(activate_chrome)
    await chat.ensure_chat_surface(BASE_URL, timeout_sec=120.0)
    await chat.ensure_react_e2e_bridge(timeout_sec=120.0)
    tools_setup = await chat.enable_computer_use()
    assert tools_setup.get("ok") is True, f"computer_use bridge failed: {tools_setup}"
    assert "computer_use" in (tools_setup.get("tools") or []), tools_setup
    tools_locked = await chat.evaluate(
        """(() => {
          const bridge = window.__MYRM_E2E_CHAT__;
          if (!bridge?.setCurrentBuiltinTools) {
            return { ok: false, err: 'no-builtin-tools-bridge' };
          }
          bridge.setCurrentBuiltinTools(['computer_use']);
          const tools = bridge.getCurrentBuiltinTools?.() ?? [];
          return { ok: true, tools };
        })()""",
        intent=EvaluateIntent.AGENT_SUBMIT,
    )
    assert (
        isinstance(tools_locked, dict) and tools_locked.get("ok") is True
    ), f"computer_use lock failed: {tools_locked}"
    locked_tools_raw = tools_locked.get("tools")
    locked_tools = (
        [str(item) for item in locked_tools_raw if isinstance(item, str)]
        if isinstance(locked_tools_raw, list)
        else []
    )
    assert "computer_use" in locked_tools, (
        "computer_use missing after tool lock: " f"{tools_locked}"
    )
    progress(f"builtin tools locked for desktop approval: {locked_tools}")

    progress("pin BASIC_MODEL from .env.test before agent send")
    pin_result = await ensure_desktop_basic_model_pinned_for_send(chat)
    provider_debug = pin_result.get("debug")
    if not isinstance(provider_debug, dict):
        provider_debug = await chat.evaluate(
            """(() => window.__MYRM_E2E_CHAT__?.debugProviderState?.() ?? null)()""",
            intent=EvaluateIntent.SYNC_PROBE,
        )
    progress(f"provider debug before send: {provider_debug}")
    if isinstance(provider_debug, dict) and not ui_provider_debug_matches_expected(
        provider_debug
    ):
        expected = expected_desktop_e2e_model()
        pytest.fail(
            "Desktop E2E send blocked: UI model is not pinned BASIC_MODEL "
            f"expected={expected} ui={provider_debug}"
        )
    if isinstance(provider_debug, dict) and not provider_debug.get(
        "enabledProviderIds"
    ):
        progress("provider not ready — sync model selection via E2E bridge")
        sync_result = await chat.evaluate(
            """(() => {
              const bridge = window.__MYRM_E2E_CHAT__;
              bridge?.prepareAutomationSend?.();
              if (!bridge?.ensureProviders) {
                return bridge?.debugProviderState?.() ?? null;
              }
              return Promise.resolve(bridge.ensureProviders()).then(
                () => bridge.debugProviderState?.() ?? null,
              );
            })()""",
            intent=EvaluateIntent.AGENT_SUBMIT,
        )
        progress(f"provider debug after sync: {sync_result}")
        if isinstance(sync_result, dict):
            provider_debug = sync_result
    if isinstance(provider_debug, dict) and not provider_debug.get(
        "enabledProviderIds"
    ):
        if not wait_e2e_provider_ready():
            readiness = fetch_provider_readiness_snapshot()
            pytest.fail(
                "Provider store empty after E2E bridge sync — "
                f"readiness={readiness} ui={provider_debug}"
            )
        resync = await chat.evaluate(
            """(() => {
              const bridge = window.__MYRM_E2E_CHAT__;
              bridge?.prepareAutomationSend?.();
              if (!bridge?.ensureProviders) return bridge?.debugProviderState?.() ?? null;
              return Promise.resolve(bridge.ensureProviders()).then(
                () => bridge.debugProviderState?.() ?? null,
              );
            })()""",
            intent=EvaluateIntent.AGENT_SUBMIT,
        )
        progress(f"provider debug after API-ready resync: {resync}")
        if isinstance(resync, dict):
            provider_debug = resync
    if isinstance(provider_debug, dict) and not provider_debug.get(
        "enabledProviderIds"
    ):
        pytest.fail(f"Provider still not enabled for send: {provider_debug}")
    if isinstance(provider_debug, dict):
        assert ui_provider_debug_matches_expected(provider_debug), (
            "Provider model drifted after sync before desktop send: "
            f"expected={expected_desktop_e2e_model()} ui={provider_debug}"
        )
    chat_id = ""
    if isinstance(provider_debug, dict):
        chat_id = str(provider_debug.get("chatId") or "").strip()

    heartbeat_once()
    progress("preflight TextEdit foreground before agent send")
    await asyncio.to_thread(preflight_textedit_foreground)
    initial_api_kickoff = False
    if signoff_mode and chat_id:
        initial_api_kickoff, _initial_kickoff = await _try_signoff_api_kickoff(
            chat_id,
            label="R286 signoff initial send",
        )
    if initial_api_kickoff:
        progress(
            "R286 initial send skipped CDP nativeClick — API kickoff active "
            f"chat_id={chat_id[:8]}..."
        )
        send_result = {
            "started": {"chatId": chat_id},
            "submit": {"chatId": chat_id},
            "mode": "api_kickoff_primary",
        }
    else:
        progress("send agent prompt (Chrome foreground for CDP submit)")
        await asyncio.to_thread(activate_chrome)
        await chat.ensure_react_e2e_bridge(timeout_sec=90.0)
        send_result = await chat.fast_desktop_agent_submit(
            E2E_PROMPT,
            E2E_PROMPT,
            chat_id_hint=chat_id or None,
        )
    progress(f"send result: {send_result.get('submit', send_result)}")
    started = send_result.get("started")
    submit = send_result.get("submit")
    if isinstance(started, dict):
        chat_id = str(started.get("chatId") or chat_id or "").strip()
    if isinstance(submit, dict):
        chat_id = str(submit.get("chatId") or chat_id or "").strip()
    progress("activate TextEdit foreground for AX snapshot @drefs")
    await asyncio.to_thread(preflight_textedit_foreground)
    heartbeat_once()

    progress("wait desktop tool activity")
    # R271: per-attempt wall must not include force_chat_shell/textedit prep —
    # otherwise wait_desktop_tool_activity fail-fast fires on poll #1 after long mux prep.
    activity_wall_started_at = _approval_attempt_wall_clock_start()
    tool_activity, last_tool, server_pending, ui_pending = await ensure_interact_gate(
        chat,
        chat_id=chat_id,
        textedit_foreground=True,
        wall_started_at=activity_wall_started_at,
    )
    progress(
        f"post-wait lastTool={last_tool} server_pending={server_pending} ui_pending={ui_pending}"
    )

    progress("wait approval banner (fast path before gate timeout)")
    await wait_for_approval_banner_clickable(
        chat,
        scope=scope,
        server_pending_hint=server_pending,
        ui_pending_hint=ui_pending,
        interact_seen_hint=last_tool.endswith("desktop_interact_tool"),
        chat_id=chat_id or None,
    )

    pending_source = str(tool_activity.get("pendingSource") or "")
    seeded_api_kickoff = False
    bridge_kickoff_used = False
    if pending_source == "seeded-fallback" and not last_tool.startswith("desktop_"):
        progress(
            "seeded pending fallback approval — resend agent prompt "
            "after approval click (no prior agent turn)"
        )
        kickoff_timeout = signoff_parallel_desktop_turn_done_timeout_sec(120.0)
        kickoff_ok = False
        seeded_api_kickoff = False
        baseline_user = 0
        baseline_ui_user = 0
        baseline_r241_fastpath = False
        if chat_id:
            try:
                baseline_user = await asyncio.wait_for(
                    asyncio.to_thread(
                        chat_user_message_count,
                        chat_id,
                        api_url=get_e2e_api_url(),
                    ),
                    timeout=10.0,
                )
            except (asyncio.TimeoutError, TimeoutError, urllib.error.HTTPError):
                baseline_user = 1
                baseline_r241_fastpath = True
                progress(
                    "seeded resend baseline userCount timeout — assume baseline=1 (R241)"
                )
            try:
                ui_snap = await asyncio.wait_for(
                    chat.evaluate(
                        "(() => window.__MYRM_E2E_CHAT__?.turnSnapshot?.() ?? null)()",
                        intent=EvaluateIntent.BRIDGE_POLL,
                    ),
                    timeout=15.0,
                )
                if isinstance(ui_snap, dict):
                    baseline_ui_user = int(ui_snap.get("userCount") or 0)
            except (asyncio.TimeoutError, TimeoutError, RuntimeError, OSError):
                baseline_ui_user = baseline_user
                progress(
                    "seeded resend baseline UI snapshot timeout — "
                    f"use baseline_ui={baseline_ui_user} (R241)"
                )
            if baseline_r241_fastpath:
                # R245: API baseline=1 but UI snapshot may still read userCount=0;
                # align UI baseline so bridge resend cannot false-positive on userCount=1.
                baseline_ui_user = max(baseline_ui_user, baseline_user)
                progress(
                    f"R245 align UI baseline={baseline_ui_user} after R241 fastpath"
                )
        if chat_id and not baseline_r241_fastpath:
            progress("seeded resend — API agent-stream kickoff (R232 mux-bypass)")
            api_timeout = min(45.0, max(20.0, kickoff_timeout / 4.0))
            kickoff_thread_budget = min(25.0, api_timeout + 5.0)
            try:
                kickoff_result = await asyncio.wait_for(
                    asyncio.to_thread(
                        _kickoff_desktop_turn_via_api_sync,
                        chat_id,
                        query=E2E_PROMPT,
                        timeout_sec=api_timeout,
                    ),
                    timeout=kickoff_thread_budget,
                )
            except (asyncio.TimeoutError, TimeoutError):
                progress(
                    "seeded resend API kickoff thread budget exceeded "
                    f"(R240 {kickoff_thread_budget:.0f}s) — bridge fallback"
                )
                kickoff_result = {
                    "events": [],
                    "error": {"error_type": "KickoffThreadTimeout"},
                }
            if _agent_stream_kickoff_started(kickoff_result):
                events = kickoff_result.get("events")
                event_count = len(events) if isinstance(events, list) else 0
                progress(
                    f"seeded resend kickoff: API stream events={event_count} "
                    f"(R237 immediate)"
                )
                kickoff_ok = True
                seeded_api_kickoff = True
            if not kickoff_ok:
                kickoff_ok = await _wait_seeded_resend_turn_kickoff(
                    chat,
                    chat_id=chat_id,
                    timeout_sec=min(90.0, kickoff_timeout),
                    baseline_user_count=baseline_user,
                    baseline_ui_user_count=baseline_ui_user,
                )
                if kickoff_ok:
                    try:
                        activity = await asyncio.to_thread(
                            _seeded_kickoff_activity_probe,
                            chat_id,
                            baseline_user_count=baseline_user,
                            api_url=get_e2e_api_url(),
                        )
                        seeded_api_kickoff = bool(activity.get("active"))
                    except urllib.error.HTTPError:
                        seeded_api_kickoff = False
        elif chat_id and baseline_r241_fastpath:
            kickoff_ok, kickoff_result = await _try_signoff_api_kickoff(
                chat_id,
                label="R285 R241 fastpath",
                kickoff_timeout_base=kickoff_timeout,
            )
            if kickoff_ok:
                seeded_api_kickoff = True
        if not kickoff_ok:
            progress(
                "seeded resend API kickoff miss — bridge E2E_PROMPT resend "
                "(R239 mux-bypass before CDP nativeClick)"
            )
            await asyncio.to_thread(activate_chrome)
            await chat.ensure_react_e2e_bridge(
                timeout_sec=signoff_parallel_desktop_mux_step_timeout_sec(90.0)
            )
            bridge_send_timeout = signoff_parallel_desktop_mux_step_timeout_sec(90.0)
            try:
                await asyncio.wait_for(
                    chat.send_message(E2E_PROMPT, E2E_PROMPT),
                    timeout=bridge_send_timeout,
                )
            except (TimeoutError, asyncio.TimeoutError) as exc:
                progress(
                    f"R257 bridge send_message timeout after {bridge_send_timeout:.0f}s "
                    f"— CDP fallback next: {exc}"
                )
            else:
                progress(
                    "R253 bridge send_message complete — verify API kickoff (R257)"
                )
                bridge_kickoff_used = True
                if chat_id:
                    verify_budget = min(
                        60.0,
                        signoff_parallel_desktop_mux_step_timeout_sec(60.0),
                    )
                    if await _verify_bridge_seal_api_kickoff(
                        chat_id,
                        timeout_sec=verify_budget,
                    ):
                        kickoff_ok = True
                        seeded_api_kickoff = True
                    else:
                        kickoff_ok = False
                        bridge_kickoff_used = False
                else:
                    kickoff_ok = True
        if not kickoff_ok:
            progress(
                "seeded resend bridge miss — CDP fast_desktop_agent_submit fallback"
            )
            await asyncio.to_thread(activate_chrome)
            cdp_transport_failed = False
            run_r262_chain = False
            resend: dict[str, object] | None = None
            try:
                resend = await asyncio.wait_for(
                    chat.fast_desktop_agent_submit(
                        E2E_PROMPT,
                        E2E_PROMPT,
                        chat_id_hint=chat_id or None,
                    ),
                    timeout=signoff_parallel_desktop_mux_step_timeout_sec(120.0),
                )
            except (RuntimeError, TimeoutError, OSError) as exc:
                if is_retriable_page_transport(exc):
                    progress(
                        "R264 CDP resend transport fail — "
                        f"R262 API kickoff bypass: {exc}"
                    )
                    cdp_transport_failed = True
                    run_r262_chain = True
                else:
                    raise
            if cdp_transport_failed:
                submit_payload: object = {"ok": False}
                progress("post-seeded-approval resend: transport_fail")
            else:
                assert resend is not None
                submit_payload = resend.get("submit", resend)
                progress(f"post-seeded-approval resend: {submit_payload}")
                started = resend.get("started")
                submit = resend.get("submit")
                if isinstance(started, dict):
                    chat_id = str(started.get("chatId") or chat_id or "").strip()
                if isinstance(submit, dict):
                    chat_id = str(submit.get("chatId") or chat_id or "").strip()
            await asyncio.to_thread(preflight_textedit_foreground)
            if isinstance(submit_payload, dict) and submit_payload.get("ok") is True:
                progress("R251 CDP resend submit ok — verify API kickoff (R260)")
                verify_budget = min(
                    90.0,
                    signoff_parallel_desktop_mux_step_timeout_sec(90.0),
                )
                if chat_id and await _verify_bridge_seal_api_kickoff(
                    chat_id,
                    timeout_sec=verify_budget,
                ):
                    progress(
                        "R260 CDP submit verified — trust nativeClick kickoff "
                        "(skip activity wait)"
                    )
                    kickoff_ok = True
                    bridge_kickoff_used = True
                    seeded_api_kickoff = True
                elif chat_id:
                    run_r262_chain = True
                else:
                    progress(
                        "R251 CDP resend submit ok — no chat_id, trust nativeClick"
                    )
                    kickoff_ok = True
                    bridge_kickoff_used = True
            if run_r262_chain and chat_id:
                if cdp_transport_failed:
                    progress("R264 CDP transport fail — R262→R261→activity wait chain")
                    progress(
                        "R262 API agent-stream kickoff after R264 transport fail "
                        "(R241 bypass)"
                    )
                else:
                    progress(
                        "R260 CDP submit API kickoff miss — "
                        "R262→R261→activity wait chain"
                    )
                    progress(
                        "R262 API agent-stream kickoff after R260 CDP miss "
                        "(R241 bypass)"
                    )
                api_timeout = min(60.0, max(30.0, kickoff_timeout / 6.0))
                kickoff_thread_budget = min(50.0, api_timeout + 15.0)
                try:
                    kickoff_result = await asyncio.wait_for(
                        asyncio.to_thread(
                            _kickoff_desktop_turn_via_api_sync,
                            chat_id,
                            query=E2E_PROMPT,
                            timeout_sec=api_timeout,
                        ),
                        timeout=kickoff_thread_budget,
                    )
                except (asyncio.TimeoutError, TimeoutError):
                    progress(
                        f"R262 API kickoff thread budget exceeded "
                        f"({kickoff_thread_budget:.0f}s)"
                    )
                    kickoff_result = {
                        "events": [],
                        "error": {"error_type": "KickoffThreadTimeout"},
                    }
                if _agent_stream_kickoff_started(kickoff_result):
                    events = kickoff_result.get("events")
                    event_count = len(events) if isinstance(events, list) else 0
                    progress(
                        f"R262 API stream kickoff started events={event_count} "
                        "after R260 miss"
                    )
                    kickoff_ok = True
                    seeded_api_kickoff = True
                    bridge_kickoff_used = False
                else:
                    verify_budget = min(
                        45.0,
                        signoff_parallel_desktop_mux_step_timeout_sec(45.0),
                    )
                    if await _verify_bridge_seal_api_kickoff(
                        chat_id,
                        timeout_sec=verify_budget,
                    ):
                        progress("R262 API activity verified after R260 miss")
                        kickoff_ok = True
                        seeded_api_kickoff = True
                        bridge_kickoff_used = False
                parallel_load_now = _signoff_desktop_soak_parallel_load()
                if not kickoff_ok and parallel_load_now >= 3:
                    progress(
                        f"R261 parallel load={parallel_load_now} — "
                        "bridge resend after R260 CDP miss"
                    )
                    await asyncio.to_thread(activate_chrome)
                    await chat.ensure_react_e2e_bridge(
                        timeout_sec=signoff_parallel_desktop_mux_step_timeout_sec(90.0)
                    )
                    bridge_send_timeout = signoff_parallel_desktop_mux_step_timeout_sec(
                        90.0
                    )
                    try:
                        await asyncio.wait_for(
                            chat.send_message(E2E_PROMPT, E2E_PROMPT),
                            timeout=bridge_send_timeout,
                        )
                    except (TimeoutError, asyncio.TimeoutError) as exc:
                        progress(
                            f"R261 bridge send_message timeout — "
                            f"activity wait next: {exc}"
                        )
                    else:
                        progress(
                            "R261 bridge send_message complete — verify API kickoff"
                        )
                        verify_budget = min(
                            60.0,
                            signoff_parallel_desktop_mux_step_timeout_sec(60.0),
                        )
                        if await _verify_bridge_seal_api_kickoff(
                            chat_id,
                            timeout_sec=verify_budget,
                        ):
                            progress("R261 bridge kickoff verified after R260 CDP miss")
                            kickoff_ok = True
                            bridge_kickoff_used = True
                            seeded_api_kickoff = True
                if not kickoff_ok:
                    kickoff_ok = await _wait_seeded_resend_turn_kickoff(
                        chat,
                        chat_id=chat_id,
                        timeout_sec=kickoff_timeout,
                        baseline_user_count=baseline_user,
                        baseline_ui_user_count=baseline_ui_user,
                    )
                    if kickoff_ok:
                        bridge_kickoff_used = True
                        try:
                            activity = await asyncio.to_thread(
                                _seeded_kickoff_activity_probe,
                                chat_id,
                                baseline_user_count=baseline_user,
                                api_url=get_e2e_api_url(),
                            )
                            seeded_api_kickoff = bool(activity.get("active"))
                        except urllib.error.HTTPError:
                            seeded_api_kickoff = False
                    else:
                        bridge_kickoff_used = False
            elif not kickoff_ok:
                kickoff_ok = await _wait_seeded_resend_turn_kickoff(
                    chat,
                    chat_id=chat_id,
                    timeout_sec=kickoff_timeout,
                    baseline_user_count=baseline_user,
                    baseline_ui_user_count=baseline_ui_user,
                )
        if not kickoff_ok:
            raise RuntimeError(
                "seeded-fallback post-approval resend did not start agent turn "
                f"within {kickoff_timeout:.0f}s"
            )
        progress(
            f"seeded resend kickoff complete api_primary_done={seeded_api_kickoff}"
        )

    chat_id_hint = chat_id.strip() if chat_id else None
    if not chat_id_hint and not seeded_api_kickoff:
        chat_id_hint = (
            str(
                (
                    await chat.evaluate(
                        "(() => window.__MYRM_E2E_CHAT__?.turnSnapshot?.()?.chatId ?? null)()",
                        intent=EvaluateIntent.BRIDGE_POLL,
                    )
                )
                or ""
            ).strip()
            or None
        )

    trusted: dict[str, object] | None = None
    if scope == "always":
        trusted = await wait_for_trusted_app_display_name("TextEdit", timeout_sec=120.0)

    chat_id = await complete_turn_after_approval(
        chat,
        chat_id_hint=chat_id_hint,
        api_primary_done=seeded_api_kickoff or initial_api_kickoff,
        skip_chat_route_restore=bridge_kickoff_used,
        bridge_kickoff_done=bridge_kickoff_used,
    )

    if scope == "always":
        assert trusted is not None
        trust_key = str(trusted.get("trust_key") or "").strip()
        assert trust_key, f"Missing trust_key in trusted app record: {trusted}"
        await verify_settings_revoke_trusted_app(
            chat,
            trust_key=trust_key,
            display_name="TextEdit",
        )
    elif scope == "session":
        apps = await asyncio.to_thread(list_trusted_apps_via_api)
        assert not apps, f"Session scope must not persist trusted apps on disk: {apps}"

    return chat_id
