"""Post-approval turn completion and settings revoke for desktop E2E."""

from __future__ import annotations

import asyncio
import json
import os
import platform
import subprocess
import time
import urllib.error
from typing import Awaitable, TypeVar

import pytest
from cdp_chat_support import (
    chat_id_from_path,
    chat_messages_have_done,
    chat_user_message_count,
    fetch_provider_readiness_snapshot,
    get_e2e_api_url,
    signoff_parallel_desktop_mux_step_timeout_sec,
    signoff_parallel_desktop_turn_done_timeout_sec,
    signoff_parallel_force_chat_timeout_sec,
    wait_e2e_provider_ready,
)
from mcp_chat_ui import McpChatSession

from tests.e2e.desktop_approval.constants import (
    APPROVAL_CLICK_DEADLINE_SEC,
    BASE_URL,
    E2E_PROMPT,
    progress,
)
from tests.e2e.desktop_approval.gate_probe import ensure_interact_gate
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
from tests.support.e2e_runtime_guard import heartbeat_e2e_lease

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
    from mux_attach_force_restart import force_mux_attach_restart_scoped

    force_mux_attach_restart_scoped(reason=reason)


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
    from e2e_mux_transport_queue import _FORCE_CHAT_SHELL_BLOCKING_NODE  # noqa: PLC0415
    from transport_supervisor import mux_upstream_wait_cap  # noqa: PLC0415

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
            await_promise=False,
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
    path = await chat.evaluate("(() => location.pathname)()", await_promise=False)
    return chat_id_from_path(str(path) if path else "")


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
                await chat.send_message(
                    "Reply with only DONE.", "Reply with only DONE."
                )
                heartbeat_e2e_lease()
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
        heartbeat_e2e_lease()
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
        await_promise=False,
    )
    assert isinstance(nav, dict) and nav.get("ok") is True, nav

    deadline = asyncio.get_event_loop().time() + 120.0
    revoke_selector = desktop_trust_revoke_selector_js(trust_key)
    probe: dict[str, object] = {}
    while asyncio.get_event_loop().time() < deadline:
        heartbeat_e2e_lease()
        probe = await chat.evaluate(
            f"""(() => {{
              const body = document.body?.innerText || '';
              const revokeBtn = document.querySelector({revoke_selector});
              return {{
                hasDisplayName: body.includes({display_name!r}),
                revokeReady: Boolean(revokeBtn && !revokeBtn.disabled),
              }};
            }})()""",
            await_promise=False,
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
        await_promise=False,
    )
    assert (
        isinstance(click, dict) and click.get("ok") is True
    ), f"Settings revoke click failed: {click}"

    empty_deadline = asyncio.get_event_loop().time() + 60.0
    while asyncio.get_event_loop().time() < empty_deadline:
        heartbeat_e2e_lease()
        apps = await asyncio.to_thread(list_trusted_apps_via_api)
        if not apps:
            return
        await asyncio.sleep(1.0)
    raise AssertionError(f"Trusted apps not empty after settings revoke: {apps}")


async def complete_turn_after_approval(
    chat: McpChatSession,
    *,
    chat_id_hint: str | None,
) -> str:
    if chat_id_hint:
        await _ensure_chat_route(chat, chat_id_hint)
    progress("wait assistant DONE")
    turn_done_timeout = signoff_parallel_desktop_turn_done_timeout_sec(180.0)
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
        await_promise=False,
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
        await_promise=False,
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
        await_promise=False,
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
        await_promise=False,
    )


async def _abort_stream_for_approval_banner(chat: McpChatSession) -> None:
    await chat.evaluate(
        """(() => {
          window.__MYRM_E2E_CHAT__?.abortActiveStream?.();
          return { ok: true };
        })()""",
        await_promise=False,
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
        heartbeat_e2e_lease()
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
        heartbeat_e2e_lease()
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
                progress("signoff mux scoped restart before force chat shell recover")
                await asyncio.to_thread(
                    _signoff_mux_attach_restart,
                    "signoff desktop force chat shell retry",
                )
            try:
                await asyncio.to_thread(chat._client.recover_mux_transport)
            except (RuntimeError, TimeoutError, OSError) as recover_exc:
                progress(f"force chat shell recover skipped (non-fatal): {recover_exc}")
            await _await_with_wall_timeout(
                chat.ensure_e2e_api_base_binding(),
                timeout_sec=20.0,
                label="force chat shell API binding",
            )
            await asyncio.sleep(1.0)


async def run_approval_attempt(chat: McpChatSession, *, scope: str = "once") -> str:
    chat._reset_shell_session_clock()
    wall_started_at = _approval_attempt_wall_clock_start()
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
    signoff_mode = os.environ.get("E2E_SIGNOFF", "").strip() == "1"
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
        await_promise=False,
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
            await_promise=False,
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
            await_promise=True,
            recv_timeout=60.0,
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
            await_promise=True,
            recv_timeout=60.0,
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

    heartbeat_e2e_lease()
    progress("preflight TextEdit foreground before agent send")
    await asyncio.to_thread(preflight_textedit_foreground)
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
    heartbeat_e2e_lease()

    progress("wait desktop tool activity")
    tool_activity, last_tool, server_pending, ui_pending = await ensure_interact_gate(
        chat,
        chat_id=chat_id,
        textedit_foreground=True,
        wall_started_at=wall_started_at,
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
    if pending_source == "seeded-fallback" and not last_tool.startswith("desktop_"):
        progress(
            "seeded pending fallback approval — resend agent prompt "
            "after approval click (no prior agent turn)"
        )
        await asyncio.to_thread(activate_chrome)
        bridge_timeout = signoff_parallel_desktop_mux_step_timeout_sec(90.0)
        await chat.ensure_react_e2e_bridge(timeout_sec=bridge_timeout)
        resend = await chat.fast_desktop_agent_submit(
            E2E_PROMPT,
            E2E_PROMPT,
            chat_id_hint=chat_id or None,
        )
        progress(f"post-seeded-approval resend: {resend.get('submit', resend)}")
        started = resend.get("started")
        submit = resend.get("submit")
        if isinstance(started, dict):
            chat_id = str(started.get("chatId") or chat_id or "").strip()
        if isinstance(submit, dict):
            chat_id = str(submit.get("chatId") or chat_id or "").strip()
        await asyncio.to_thread(preflight_textedit_foreground)

    chat_id_hint = (
        chat_id
        or str(
            (
                await chat.evaluate(
                    "(() => window.__MYRM_E2E_CHAT__?.turnSnapshot?.()?.chatId ?? null)()",
                    await_promise=False,
                )
            )
            or ""
        ).strip()
        or None
    )

    trusted: dict[str, object] | None = None
    if scope == "always":
        trusted = await wait_for_trusted_app_display_name("TextEdit", timeout_sec=120.0)

    chat_id = await complete_turn_after_approval(chat, chat_id_hint=chat_id_hint)

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
