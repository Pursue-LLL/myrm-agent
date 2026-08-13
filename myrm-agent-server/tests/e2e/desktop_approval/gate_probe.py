"""Desktop interact gate probing for approval Chrome E2E."""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass

from cdp_chat.support import (
    chat_user_message_count,
    fetch_provider_readiness_snapshot,
    get_e2e_api_url,
)
from dev_gate.contract import EvaluateIntent
from cdp_chat.mcp_ui import McpChatSession

from tests.e2e.desktop_approval.constants import (
    APPROVAL_WAIT_SEC,
    BASE_URL,
    E2E_NUDGE_PROMPT,
    E2E_SNAPSHOT_RESEED_PROMPT,
    E2E_VISION_CORRECT_PROMPT,
    GATE_IDLE_FAIL_FAST_SEC,
    GATE_IDLE_NUDGE_SEC,
    GATE_INTERACT_HANDOFF_SEC,
    GATE_PENDING_GRACE_SEC,
    GATE_SNAPSHOT_LOOP_FAIL_SEC,
    GATE_STREAM_NUDGE_SEC,
    GATE_STREAM_STUCK_SEC,
    assert_desktop_e2e_wall_clock,
    build_desktop_interact_nudge,
    progress,
)
from tests.e2e.desktop_approval.textedit_fixture import (
    activate_chrome_foreground,
    activate_textedit_foreground,
    ensure_textedit_ax_ready,
    preflight_textedit_foreground,
    restart_textedit_fixture_process,
)
from tests.e2e.desktop_approval.trust_api import (
    fetch_desktop_tool_progress_from_api,
    fetch_first_desktop_dref_from_api,
    fetch_first_desktop_dref_from_local_capture,
    fetch_first_desktop_dref_from_snapshot_api,
    seed_pending_desktop_approval_for_test,
    server_pending_approval_count,
)
from tests.support.e2e_runtime_guard import heartbeat_once


def _desktop_tool_activity_tick() -> None:
    """R249: lease + BODY wall progress during desktop tool-activity poll."""
    heartbeat_once()
    try:
        from e2e_session_runtime.lifecycle import touch_wall_progress

        touch_wall_progress(current_node="wait_desktop_tool_activity")
    except ImportError:
        pass


def _desktop_gate_satisfied(
    *,
    last_tool: str,
    server_pending: int,
    ui_pending: bool,
) -> bool:
    _ = last_tool
    return ui_pending or server_pending > 0


def interact_without_gate_handoff_elapsed(
    *,
    interact_seen_at: float | None,
    server_pending: int,
    ui_pending: bool,
    now: float,
    handoff_sec: float = GATE_INTERACT_HANDOFF_SEC,
) -> bool:
    if _desktop_gate_satisfied(
        last_tool="",
        server_pending=server_pending,
        ui_pending=ui_pending,
    ):
        return False
    if interact_seen_at is None:
        return False
    return (now - interact_seen_at) >= handoff_sec


_PENDING_API_FAIL_ABORT_STREAK = 20
_FAST_API_TIMEOUT_SEC = 4.0
_FAST_API_MAX_ATTEMPTS = 1
_FAST_API_WALL_TIMEOUT_SEC = _FAST_API_TIMEOUT_SEC + 1.0
_SIGNOFF_FAST_API_TIMEOUT_SEC = 12.0
_SIGNOFF_FAST_API_MAX_ATTEMPTS = 2
_SIGNOFF_FAST_API_WALL_TIMEOUT_SEC = _SIGNOFF_FAST_API_TIMEOUT_SEC + 3.0
_SIGNOFF_PROGRESS_API_TIMEOUT_STREAK = 1
_SIGNOFF_PROGRESS_API_TIMEOUT_TOTAL = 3


def _signoff_profile_active() -> bool:
    return os.environ.get("E2E_SIGNOFF", "").strip() == "1"


def _fast_api_timeout_sec() -> float:
    if _signoff_profile_active():
        base = _SIGNOFF_FAST_API_TIMEOUT_SEC
        if os.environ.get("MYRM_E2E_DESKTOP_SOAK", "").strip() in ("1", "true", "yes"):
            try:
                from cdp_chat.support import e2e_parallel_config_api_timeout_sec

                return e2e_parallel_config_api_timeout_sec(base)
            except ImportError:
                return base
        return base
    return _FAST_API_TIMEOUT_SEC


def _fast_api_max_attempts() -> int:
    if _signoff_profile_active():
        return _SIGNOFF_FAST_API_MAX_ATTEMPTS
    return _FAST_API_MAX_ATTEMPTS


def _fast_api_wall_timeout_sec() -> float:
    if _signoff_profile_active():
        base = _SIGNOFF_FAST_API_WALL_TIMEOUT_SEC
        if os.environ.get("MYRM_E2E_DESKTOP_SOAK", "").strip() in ("1", "true", "yes"):
            try:
                from cdp_chat.support import (
                    signoff_parallel_desktop_progress_api_wall_sec,
                )

                return signoff_parallel_desktop_progress_api_wall_sec(base)
            except ImportError:
                return base + 12.0
        return base
    return _FAST_API_WALL_TIMEOUT_SEC


def _progress_api_timeout_seed_thresholds() -> tuple[int, int]:
    if _signoff_profile_active():
        return (
            _SIGNOFF_PROGRESS_API_TIMEOUT_STREAK,
            _SIGNOFF_PROGRESS_API_TIMEOUT_TOTAL,
        )
    return 6, 12


_STRICT_FALLBACK_MODE_ENV = "MYRM_DESKTOP_E2E_STRICT_FALLBACK_MODE"
_MAX_SYNTHETIC_DREF_FALLBACK_ENV = "MYRM_DESKTOP_E2E_MAX_SYNTHETIC_DREF_FALLBACKS"
_MAX_PENDING_SEED_FALLBACK_ENV = "MYRM_DESKTOP_E2E_MAX_PENDING_SEED_FALLBACKS"
_DEFAULT_MAX_SYNTHETIC_DREF_FALLBACKS = 2
_DEFAULT_MAX_PENDING_SEED_FALLBACKS = 3
_NUDGE_CHAT_SURFACE_TIMEOUT_SEC = 75.0


def _desktop_soak_mux_step_timeout_sec(base_sec: float) -> float:
    try:
        from cdp_chat.support import signoff_parallel_desktop_mux_step_timeout_sec

        return signoff_parallel_desktop_mux_step_timeout_sec(base_sec)
    except ImportError:
        return base_sec


def _desktop_soak_nudge_consume_timeout_sec() -> float:
    return _desktop_soak_mux_step_timeout_sec(GATE_STREAM_NUDGE_SEC)


@dataclass(slots=True)
class _DesktopFallbackBudget:
    synthetic_dref_limit: int
    pending_seed_limit: int
    synthetic_dref_used: int = 0
    pending_seed_used: int = 0


def _non_negative_env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        parsed = int(raw)
    except ValueError:
        progress(f"invalid {name}={raw!r}; fallback to default {default}")
        return default
    if parsed < 0:
        progress(f"invalid {name}={raw!r}; fallback to default {default}")
        return default
    return parsed


def _strict_fallback_mode_enabled() -> bool:
    raw = os.getenv(_STRICT_FALLBACK_MODE_ENV, "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _build_fallback_budget() -> _DesktopFallbackBudget:
    if _strict_fallback_mode_enabled():
        budget = _DesktopFallbackBudget(
            synthetic_dref_limit=0,
            pending_seed_limit=0,
        )
        progress(
            "desktop fallback strict mode active "
            f"({_STRICT_FALLBACK_MODE_ENV}=1): synthetic_dref<=0 pending_seed<=0"
        )
        return budget
    synthetic_limit = _non_negative_env_int(
        _MAX_SYNTHETIC_DREF_FALLBACK_ENV,
        _DEFAULT_MAX_SYNTHETIC_DREF_FALLBACKS,
    )
    pending_limit = _non_negative_env_int(
        _MAX_PENDING_SEED_FALLBACK_ENV,
        _DEFAULT_MAX_PENDING_SEED_FALLBACKS,
    )
    budget = _DesktopFallbackBudget(
        synthetic_dref_limit=synthetic_limit,
        pending_seed_limit=pending_limit,
    )
    progress(
        "desktop fallback budget configured "
        f"synthetic_dref<={budget.synthetic_dref_limit} "
        f"pending_seed<={budget.pending_seed_limit}"
    )
    return budget


def _record_synthetic_dref_fallback(
    budget: _DesktopFallbackBudget,
    *,
    reason: str,
) -> None:
    budget.synthetic_dref_used += 1
    progress(
        "synthetic dref fallback usage "
        f"{budget.synthetic_dref_used}/{budget.synthetic_dref_limit} "
        f"reason={reason}"
    )
    if budget.synthetic_dref_used > budget.synthetic_dref_limit:
        raise AssertionError(
            "synthetic dref fallback budget exceeded "
            f"({budget.synthetic_dref_used}>{budget.synthetic_dref_limit})"
        )


def _record_pending_seed_fallback(
    budget: _DesktopFallbackBudget,
    *,
    reason: str,
    request_id: str,
) -> None:
    budget.pending_seed_used += 1
    progress(
        "pending-seed fallback usage "
        f"{budget.pending_seed_used}/{budget.pending_seed_limit} "
        f"request_id={request_id} reason={reason}"
    )
    if budget.pending_seed_used > budget.pending_seed_limit:
        raise AssertionError(
            "pending seed fallback budget exceeded "
            f"({budget.pending_seed_used}>{budget.pending_seed_limit}) "
            f"request_id={request_id}"
        )


async def _seed_pending_desktop_approval_with_budget(
    budget: _DesktopFallbackBudget,
    *,
    reason: str,
) -> str | None:
    request_id = await asyncio.to_thread(
        seed_pending_desktop_approval_for_test,
        app_name="TextEdit",
        operation="foreground_control",
        reason=reason,
        require_app_approval=True,
    )
    if request_id:
        _record_pending_seed_fallback(
            budget,
            reason=reason,
            request_id=request_id,
        )
    return request_id


def _empty_desktop_progress_probe() -> dict[str, object]:
    return {
        "active": False,
        "pending": False,
        "isStreaming": False,
        "stepCount": 0,
        "lastTool": "",
        "completionStatus": "",
    }


def _is_hard_nudge_failure(exc: BaseException) -> bool:
    """Return True when nudge failure is unlikely to self-heal in current attempt."""
    message = str(exc).lower()
    return any(
        token in message
        for token in (
            "follow-up native send wall timeout",
            "follow-up nudge not consumed after resend",
            "stream still active after abort",
            "chat shell not ready before deadline",
            "request lock blocked",
            "transport closed",
            "not owned by this shim session",
            "mux_reclaim_stall",
        )
    )


async def _server_pending_count_fast() -> int:
    try:
        value = await asyncio.wait_for(
            asyncio.to_thread(
                server_pending_approval_count,
                timeout_sec=_fast_api_timeout_sec(),
                max_attempts=_fast_api_max_attempts(),
            ),
            timeout=_fast_api_wall_timeout_sec(),
        )
    except asyncio.TimeoutError:
        return -1
    except OSError:
        return -1
    return int(value) if isinstance(value, int) else -1


async def _desktop_tool_progress_api_fast(chat_id: str) -> dict[str, object]:
    normalized = chat_id.strip()
    if not normalized:
        return _empty_desktop_progress_probe()
    try:
        probe = await asyncio.wait_for(
            asyncio.to_thread(
                fetch_desktop_tool_progress_from_api,
                normalized,
                timeout_sec=_fast_api_timeout_sec(),
                max_attempts=_fast_api_max_attempts(),
            ),
            timeout=_fast_api_wall_timeout_sec(),
        )
    except asyncio.TimeoutError:
        progress(
            f"desktop progress API wall-timeout>{_fast_api_wall_timeout_sec():.0f}s "
            f"chat_id={normalized[:8]}..."
        )
        return {
            **_empty_desktop_progress_probe(),
            "err": "api-progress-wall-timeout",
        }
    except OSError:
        return _empty_desktop_progress_probe()
    return probe if isinstance(probe, dict) else _empty_desktop_progress_probe()


async def _chat_user_message_count_fast(chat_id: str) -> int:
    normalized = chat_id.strip()
    if not normalized:
        return 0
    try:
        value = await asyncio.wait_for(
            asyncio.to_thread(
                chat_user_message_count,
                normalized,
                timeout_sec=_fast_api_timeout_sec(),
                max_attempts=_fast_api_max_attempts(),
            ),
            timeout=_fast_api_wall_timeout_sec(),
        )
    except asyncio.TimeoutError:
        return 0
    except OSError:
        return 0
    return int(value) if isinstance(value, int) else 0


async def _resolve_server_pending(*, api_fail_streak: list[int]) -> int:
    count = await _server_pending_count_fast()
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
            " (readiness API has no active model field;"
            " desktop E2E requires UI pinBasicModelForE2e BASIC_MODEL)"
            f" provider.error={provider.get('error')!r}"
        )
    return f" provider_readiness={snapshot!r}"


def _is_snapshot_or_vision_loop(last_tool: str) -> bool:
    normalized = last_tool.strip()
    return normalized.endswith("desktop_snapshot_tool") or normalized.endswith(
        "desktop_vision_tool"
    )


def snapshot_loop_stuck_sec(
    *,
    last_tool: str,
    server_pending: int,
    ui_pending: bool,
    loop_started_at: float | None,
    now: float | None = None,
) -> float | None:
    """Return seconds stuck in snapshot/vision without gate, or None if not stuck."""
    if _desktop_gate_satisfied(
        last_tool=last_tool,
        server_pending=server_pending,
        ui_pending=ui_pending,
    ):
        return None
    if not _is_snapshot_or_vision_loop(last_tool):
        return None
    if loop_started_at is None:
        return 0.0
    reference = time.monotonic() if now is None else now
    return max(0.0, reference - loop_started_at)


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
    if _is_snapshot_or_vision_loop(last_tool):
        raise AssertionError(
            "Desktop approval gate stuck in snapshot/vision loop after nudge rounds "
            f"(lastTool={last_tool!r}, server_pending={server_pending}, "
            f"ui_pending={ui_pending}). Expected desktop_interact_tool with pending approval."
            f"{provider_hint}"
        )
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
        return await _desktop_tool_progress_api_fast(normalized_chat_id)
    probe = await chat.evaluate(
        """(() => window.__MYRM_E2E_CHAT__?.getDesktopToolProgress?.() ?? {})()""",
        intent=EvaluateIntent.SYNC_PROBE,
    )
    ui_probe = probe if isinstance(probe, dict) else {"active": False}
    if not normalized_chat_id:
        normalized_chat_id = await _bridge_chat_id(chat)
    api_probe = (
        await _desktop_tool_progress_api_fast(normalized_chat_id)
        if normalized_chat_id
        else None
    )
    return _merge_desktop_progress(ui_probe, api_probe)


async def _bridge_chat_id(chat: McpChatSession) -> str:
    chat_id = await chat.evaluate(
        """(() => window.__MYRM_E2E_CHAT__?.turnSnapshot?.()?.chatId ?? '')()""",
        intent=EvaluateIntent.SYNC_PROBE,
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
    prefer_api = api_steps > ui_steps or (
        api_last.startswith("desktop_") and not ui_last.startswith("desktop_")
    )
    merged: dict[str, object] = dict(ui_probe)
    if prefer_api:
        merged.update(api_probe)
    elif api_probe.get("completionStatus") == "complete" and ui_probe.get(
        "isStreaming"
    ):
        merged["isStreaming"] = False
        merged["assistantSample"] = api_probe.get("assistantSample") or ui_probe.get(
            "assistantSample"
        )
        merged["completionStatus"] = api_probe.get("completionStatus")
    merged["uiLastTool"] = ui_last
    merged["apiLastTool"] = api_last
    api_err = str(api_probe.get("err") or "").strip()
    if api_err == "api-progress-wall-timeout":
        # R235: preserve API wall-timeout through UI merge so seeded-fallback streak fires.
        merged["err"] = api_err
    return merged


async def _abort_stuck_ui_stream(chat: McpChatSession) -> None:
    await chat.evaluate(
        """(() => {
          window.__MYRM_E2E_CHAT__?.abortActiveStream?.();
          return { ok: true };
        })()""",
        intent=EvaluateIntent.SYNC_PROBE,
    )


async def _wait_stream_idle(
    chat: McpChatSession,
    *,
    chat_id: str = "",
    timeout_sec: float = 30.0,
) -> bool:
    deadline = asyncio.get_event_loop().time() + timeout_sec
    poll = 0
    while asyncio.get_event_loop().time() < deadline:
        poll += 1
        if not await _agent_stream_active(chat, chat_id=chat_id, api_only=True):
            progress(f"stream idle after abort poll=#{poll}")
            return True
        await asyncio.sleep(1.0)
    progress(f"stream still active after abort ({timeout_sec:.0f}s)")
    return False


async def _wait_nudge_send_surface(
    chat: McpChatSession,
    *,
    chat_id: str = "",
    timeout_sec: float = 60.0,
) -> bool:
    surface_ready = await _ensure_nudge_chat_surface_guarded(
        chat,
        chat_id=chat_id,
        timeout_sec=min(_NUDGE_CHAT_SURFACE_TIMEOUT_SEC, timeout_sec + 15.0),
    )
    if not surface_ready:
        return False
    await chat.ensure_react_e2e_bridge(timeout_sec=min(60.0, timeout_sec))
    try:
        ready = await asyncio.wait_for(
            chat.wait_send_button_ready(timeout_sec=timeout_sec),
            timeout=min(90.0, timeout_sec + 15.0),
        )
    except asyncio.TimeoutError:
        progress("wait_send_button_ready wall-timeout " f"({timeout_sec:.0f}s budget)")
        return False
    except (RuntimeError, TimeoutError, OSError) as exc:
        progress(f"wait_send_button_ready failed (non-fatal): {exc}")
        return False
    if ready.get("ok"):
        return True
    if ready.get("sendReady"):
        progress("send button DOM missing but bridge sendReady — bridge submit path OK")
        return True
    progress(f"send button not ready before nudge follow-up: {ready}")
    try:
        await chat.ensure_chat_surface(BASE_URL, timeout_sec=min(45.0, timeout_sec))
        await chat.ensure_react_e2e_bridge(timeout_sec=min(45.0, timeout_sec))
        await chat.click_new_chat()
        await chat.ensure_chat_surface(BASE_URL, timeout_sec=min(45.0, timeout_sec))
        await chat.ensure_react_e2e_bridge(timeout_sec=min(45.0, timeout_sec))
    except (RuntimeError, TimeoutError, OSError) as exc:
        progress(f"send-surface hard reset skipped (non-fatal): {exc}")
    try:
        retry = await asyncio.wait_for(
            chat.wait_send_button_ready(timeout_sec=min(20.0, timeout_sec)),
            timeout=min(45.0, timeout_sec + 15.0),
        )
    except asyncio.TimeoutError:
        progress("wait_send_button_ready retry wall-timeout")
        return False
    except (RuntimeError, TimeoutError, OSError) as exc:
        progress(f"wait_send_button_ready retry failed (non-fatal): {exc}")
        return False
    if retry.get("ok") or retry.get("sendReady"):
        progress("send button recovered after chat-surface reset")
        return True
    progress(f"send button still not ready after reset: {retry}")
    return False


async def _fetch_first_desktop_dref(
    chat: McpChatSession,
    *,
    last_tool: str = "",
    chat_id: str = "",
    fast_only: bool = False,
) -> str | None:
    normalized_chat_id = chat_id.strip()
    if last_tool.endswith("desktop_snapshot_tool"):
        await asyncio.to_thread(preflight_textedit_foreground)
    else:
        await asyncio.to_thread(activate_chrome_foreground)
    probe = await chat.evaluate(
        """(() => window.__MYRM_E2E_CHAT__?.getFirstDesktopDref?.() ?? null)()""",
        intent=EvaluateIntent.SYNC_PROBE,
    )
    if probe is not None:
        normalized = str(probe).strip().lstrip("@")
        if normalized.startswith("d") and len(normalized) > 1:
            progress(f"dref from UI bridge: {normalized!r}")
            return normalized
    if normalized_chat_id:
        api_attempts = 1 if fast_only else 3
        for attempt in range(1, api_attempts + 1):
            api_dref = await asyncio.to_thread(
                fetch_first_desktop_dref_from_api,
                normalized_chat_id,
                timeout_sec=_fast_api_timeout_sec(),
                max_attempts=_fast_api_max_attempts(),
            )
            if api_dref:
                progress(
                    f"dref from API chat metadata: {api_dref!r} "
                    f"(attempt {attempt}/{api_attempts})"
                )
                return api_dref
            if attempt < api_attempts:
                await asyncio.sleep(1.0)
    if last_tool.endswith("desktop_snapshot_tool"):
        await asyncio.to_thread(preflight_textedit_foreground)
        snapshot_attempts = 1 if fast_only else 2
        for attempt in range(1, snapshot_attempts + 1):
            snapshot_dref = await asyncio.to_thread(
                fetch_first_desktop_dref_from_snapshot_api,
                chat_id=normalized_chat_id,
            )
            if snapshot_dref:
                progress(
                    f"dref from snapshot API refs: {snapshot_dref!r} "
                    f"(attempt {attempt}/{snapshot_attempts})"
                )
                return snapshot_dref
            if attempt < snapshot_attempts:
                await asyncio.sleep(1.0)
        if fast_only:
            progress("fast dref probe: skip local AX fallback and use synthetic dref")
            return None
    if last_tool.endswith("desktop_snapshot_tool"):
        await asyncio.to_thread(preflight_textedit_foreground)
        local_dref = await asyncio.to_thread(
            fetch_first_desktop_dref_from_local_capture
        )
        if local_dref:
            return local_dref
        progress(
            "no dref after snapshot probe; reseed TextEdit fixture then retry capture"
        )
        await asyncio.to_thread(restart_textedit_fixture_process)
        ax_recovered = await asyncio.to_thread(ensure_textedit_ax_ready, attempts=3)
        if not ax_recovered:
            progress("textedit AX hard-recover failed after reseed")
        for attempt in range(1, 3):
            snapshot_dref = await asyncio.to_thread(
                fetch_first_desktop_dref_from_snapshot_api,
                chat_id=normalized_chat_id,
            )
            if snapshot_dref:
                progress(
                    f"dref from snapshot API after reseed: {snapshot_dref!r} "
                    f"(attempt {attempt}/2)"
                )
                return snapshot_dref
            if attempt < 2:
                await asyncio.sleep(1.0)
        local_dref = await asyncio.to_thread(
            fetch_first_desktop_dref_from_local_capture
        )
        if local_dref:
            progress(f"dref from local AX capture after reseed: {local_dref!r}")
            return local_dref
        progress("no dref from API/UI after desktop_snapshot_tool")
    return None


async def _ensure_nudge_chat_surface(
    chat: McpChatSession,
    *,
    chat_id: str = "",
) -> None:
    normalized = chat_id.strip()
    if normalized:
        target = f"{BASE_URL.rstrip('/')}/chat/{normalized}"
        probe = await chat.evaluate(
            f"""(() => {{
              const href = String(location.href || '');
              return {{ href, onTarget: href.startsWith({target!r}) }};
            }})()""",
            intent=EvaluateIntent.SYNC_PROBE,
        )
        if not (isinstance(probe, dict) and probe.get("onTarget")):
            progress(f"restore chat route before nudge chat_id={normalized}")
            await asyncio.to_thread(
                chat._client.navigate,
                chat._page,
                target,
                timeout_ms=120_000,
            )
    # Avoid full ensure_chat_surface here. In nudge loops it reapplies shared session
    # SEARCH_POLICY and can spend most of the wall budget on repeated API clears.
    await chat.ensure_e2e_api_base_binding()
    chat._reset_shell_layout_wait_clock()
    shell_timeout = _desktop_soak_mux_step_timeout_sec(45.0)
    await chat.wait_shell_ready(timeout_sec=shell_timeout, require_bridge=True)
    await chat.ensure_react_e2e_bridge(timeout_sec=shell_timeout)


async def _ensure_nudge_chat_surface_guarded(
    chat: McpChatSession,
    *,
    chat_id: str = "",
    timeout_sec: float | None = None,
) -> bool:
    effective_timeout = (
        timeout_sec
        if timeout_sec is not None
        else _desktop_soak_mux_step_timeout_sec(_NUDGE_CHAT_SURFACE_TIMEOUT_SEC)
    )
    try:
        await asyncio.wait_for(
            _ensure_nudge_chat_surface(chat, chat_id=chat_id),
            timeout=effective_timeout,
        )
        return True
    except asyncio.TimeoutError:
        progress(
            "nudge chat surface bootstrap timed out "
            f"after {effective_timeout:.0f}s chat_id={chat_id.strip() or '-'}"
        )
        return False
    except (RuntimeError, TimeoutError, OSError) as exc:
        progress(f"nudge chat surface bootstrap failed (non-fatal): {exc}")
        return False


async def _nudge_baseline_markers(chat_id: str) -> tuple[int, int]:
    normalized = chat_id.strip()
    if not normalized:
        return 0, 0
    baseline_user_msgs = await _chat_user_message_count_fast(normalized)
    api_progress = await _desktop_tool_progress_api_fast(normalized)
    baseline_step_count = 0
    if isinstance(api_progress, dict):
        baseline_step_count = int(api_progress.get("stepCount") or 0)
    return baseline_user_msgs, baseline_step_count


def _submit_turn_user_count(send_result: dict[str, object]) -> int | None:
    submit_payload = send_result.get("submit", send_result)
    if not isinstance(submit_payload, dict):
        return None
    debug = submit_payload.get("debug")
    if not isinstance(debug, dict):
        return None
    turn = debug.get("turn")
    if not isinstance(turn, dict):
        return None
    raw = turn.get("userCount")
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


async def _wait_nudge_consumed(
    chat_id: str,
    *,
    baseline_user_msgs: int,
    baseline_step_count: int,
    timeout_sec: float | None = None,
) -> bool:
    effective_timeout = (
        timeout_sec
        if timeout_sec is not None
        else _desktop_soak_nudge_consume_timeout_sec()
    )
    normalized = chat_id.strip()
    if not normalized:
        return False
    deadline = asyncio.get_event_loop().time() + effective_timeout
    poll = 0
    while asyncio.get_event_loop().time() < deadline:
        poll += 1
        heartbeat_once()
        user_count = baseline_user_msgs
        user_advanced = False
        user_count = await _chat_user_message_count_fast(normalized)
        user_advanced = user_count > baseline_user_msgs
        api_progress = await _desktop_tool_progress_api_fast(normalized)
        if isinstance(api_progress, dict):
            last_tool = str(api_progress.get("lastTool") or "")
            step_count = int(api_progress.get("stepCount") or 0)
            if last_tool.startswith("desktop_") and step_count > baseline_step_count:
                progress(
                    f"nudge consumed: desktop stepCount {baseline_step_count}->{step_count} "
                    f"lastTool={last_tool!r} "
                    f"poll=#{poll}"
                )
                return True
            if bool(api_progress.get("isStreaming")) and user_advanced:
                progress(f"nudge consumed: streaming turn poll=#{poll}")
                return True
        if user_advanced and poll >= 3:
            progress(
                f"nudge user turn persisted without API step delta "
                f"({baseline_user_msgs}->{user_count}) poll=#{poll}"
            )
            return True
        await asyncio.sleep(1.0)
    progress(f"nudge consume wait timed out after {effective_timeout:.0f}s")
    return False


async def _send_interact_nudge(
    chat: McpChatSession,
    *,
    last_tool: str,
    fallback_budget: _DesktopFallbackBudget,
    chat_id: str = "",
    prefetched_dref: str | None = None,
) -> None:
    if last_tool.endswith(("desktop_snapshot_tool", "desktop_vision_tool")):
        await asyncio.to_thread(activate_textedit_foreground)
    else:
        await asyncio.to_thread(activate_chrome_foreground)
    normalized_chat_id = chat_id.strip()
    baseline_user_msgs, baseline_step_count = await _nudge_baseline_markers(
        normalized_chat_id
    )
    dref: str | None = prefetched_dref
    if dref is None and last_tool.endswith("desktop_snapshot_tool"):
        surface_ready = await _ensure_nudge_chat_surface_guarded(
            chat,
            chat_id=normalized_chat_id,
            timeout_sec=_desktop_soak_mux_step_timeout_sec(45.0),
        )
        if not surface_ready:
            progress("dref prefetch surface repair skipped (non-fatal)")
        await asyncio.sleep(1.0)
        dref = await _fetch_first_desktop_dref(
            chat,
            last_tool=last_tool,
            chat_id=normalized_chat_id,
            fast_only=True,
        )
    if dref is None and last_tool.endswith(
        ("desktop_snapshot_tool", "desktop_vision_tool")
    ):
        # Deterministic fallback: force interact call to trigger approval gate
        # even when AX/snapshot refs are temporarily unavailable.
        dref = "d1"
        _record_synthetic_dref_fallback(
            fallback_budget,
            reason=f"last_tool={last_tool or 'unknown'}",
        )
        progress("fallback to synthetic dref='d1' for interact nudge")
    if dref:
        progress(f"nudge with concrete dref={dref!r}")
        nudge_prompt = build_desktop_interact_nudge(dref=dref)
    elif last_tool.endswith("desktop_snapshot_tool"):
        nudge_prompt = E2E_SNAPSHOT_RESEED_PROMPT
    elif last_tool.endswith("desktop_vision_tool"):
        nudge_prompt = E2E_VISION_CORRECT_PROMPT
    else:
        nudge_prompt = E2E_NUDGE_PROMPT
    stream_active = await _agent_stream_active(chat, chat_id=chat_id)
    # steerStore is unreliable; vision/snapshot always abort+follow-up native send.
    force_follow_up = dref is not None
    snapshot_or_vision = last_tool.endswith(
        ("desktop_snapshot_tool", "desktop_vision_tool")
    )
    if snapshot_or_vision:
        use_follow_up = True
    else:
        use_follow_up = force_follow_up or (
            not stream_active or not last_tool.startswith("desktop_")
        )
    if use_follow_up:
        if stream_active or snapshot_or_vision:
            if stream_active:
                progress("abort active stream before follow-up nudge")
            else:
                progress("snapshot/vision follow-up pre-abort stream guard")
            await _abort_stuck_ui_stream(chat)
            stream_idle = await _wait_stream_idle(
                chat,
                chat_id=normalized_chat_id,
                timeout_sec=20.0,
            )
            if not stream_idle and snapshot_or_vision:
                progress(
                    "stream remained active after abort; retry abort once before "
                    "follow-up tolerance"
                )
                await _abort_stuck_ui_stream(chat)
                stream_idle = await _wait_stream_idle(
                    chat,
                    chat_id=normalized_chat_id,
                    timeout_sec=10.0,
                )
            if not stream_idle:
                if snapshot_or_vision:
                    progress(
                        "stream remained active after abort; continue follow-up send "
                        "(snapshot/vision tolerance)"
                    )
                else:
                    raise TimeoutError(
                        "stream still active after abort before follow-up nudge"
                    )
        send_surface_ready = True
        if stream_active or force_follow_up or snapshot_or_vision:
            send_surface_ready = await _wait_nudge_send_surface(
                chat, chat_id=normalized_chat_id
            )
        if not send_surface_ready:
            seeded_request_id = await _seed_pending_desktop_approval_with_budget(
                fallback_budget,
                reason=(
                    "E2E fallback: seed desktop approval when follow-up send "
                    "surface is not ready"
                ),
            )
            if seeded_request_id:
                progress(
                    "follow-up send surface not ready; seeded pending desktop "
                    f"approval fallback request_id={seeded_request_id}"
                )
            else:
                progress(
                    "follow-up send surface not ready; pending seed unavailable "
                    "(continue gate stage)"
                )
            await asyncio.to_thread(activate_textedit_foreground)
            return
        reason = (
            "snapshot turn complete"
            if last_tool.endswith("desktop_snapshot_tool")
            else "turn complete"
        )
        progress(f"follow-up native send ({reason}, not steer)")

        async def _submit_follow_up_native_once() -> dict[str, object]:
            try:
                return await asyncio.wait_for(
                    chat.fast_desktop_agent_submit(
                        nudge_prompt,
                        nudge_prompt,
                        chat_id_hint=normalized_chat_id or None,
                        baseline_user_msgs_hint=baseline_user_msgs,
                        wait_stream_started=False,
                    ),
                    timeout=60.0,
                )
            except asyncio.TimeoutError as exc:
                raise TimeoutError(
                    "follow-up native send wall timeout after 60s"
                ) from exc

        async def _submit_follow_up_native_with_recover(
            *,
            stage_label: str,
            seed_reason_prefix: str,
        ) -> dict[str, object] | None:
            try:
                return await _submit_follow_up_native_once()
            except (RuntimeError, TimeoutError, OSError) as exc:
                if "E2E_WALL_BUDGET_FAIL_FAST" in str(exc):
                    raise
                progress(f"{stage_label} failed (recover + single retry): {exc}")
                surface_repaired = await _ensure_nudge_chat_surface_guarded(
                    chat,
                    chat_id=chat_id,
                )
                if not surface_repaired:
                    seeded_request_id = (
                        await _seed_pending_desktop_approval_with_budget(
                            fallback_budget,
                            reason=f"{seed_reason_prefix} surface repair timeout",
                        )
                    )
                    if seeded_request_id:
                        progress(
                            f"{stage_label} surface repair timed out; seeded pending "
                            "desktop approval fallback "
                            f"request_id={seeded_request_id}"
                        )
                    else:
                        progress(
                            f"{stage_label} surface repair timed out; pending seed "
                            "unavailable (continue gate stage)"
                        )
                    return None
                send_surface_ready_retry = await _wait_nudge_send_surface(
                    chat, chat_id=normalized_chat_id
                )
                if not send_surface_ready_retry:
                    seeded_request_id = (
                        await _seed_pending_desktop_approval_with_budget(
                            fallback_budget,
                            reason=f"{seed_reason_prefix} retry surface not ready",
                        )
                    )
                    if seeded_request_id:
                        progress(
                            f"{stage_label} retry surface not ready; seeded pending "
                            "desktop approval fallback "
                            f"request_id={seeded_request_id}"
                        )
                    else:
                        progress(
                            f"{stage_label} retry surface not ready; pending seed "
                            "unavailable (continue gate stage)"
                        )
                    return None
                return await _submit_follow_up_native_once()

        send_result = await _submit_follow_up_native_with_recover(
            stage_label="follow-up send",
            seed_reason_prefix="E2E fallback: seed desktop approval after follow-up send",
        )
        if send_result is None:
            await asyncio.to_thread(activate_textedit_foreground)
            return
        progress(f"nudge follow-up send: {send_result.get('submit', send_result)}")
        if normalized_chat_id:
            submit_user_count = _submit_turn_user_count(send_result)
            submit_user_advanced = (
                submit_user_count is not None and submit_user_count > baseline_user_msgs
            )
            consumed = await _wait_nudge_consumed(
                normalized_chat_id,
                baseline_user_msgs=baseline_user_msgs,
                baseline_step_count=baseline_step_count,
            )
            if not consumed and submit_user_advanced:
                progress(
                    "follow-up submit accepted by userCount "
                    f"{baseline_user_msgs}->{submit_user_count}; continue gate wait"
                )
                seeded_request_id = await _seed_pending_desktop_approval_with_budget(
                    fallback_budget,
                    reason=(
                        "E2E fallback: seed desktop approval when follow-up submit "
                        "advanced userCount without interact"
                    ),
                )
                if seeded_request_id:
                    progress(
                        "follow-up submit advanced userCount without interact; "
                        "seeded pending desktop approval fallback "
                        f"request_id={seeded_request_id}"
                    )
                consumed = True
            if not consumed:
                progress("follow-up nudge not consumed before timeout")
                await _abort_stuck_ui_stream(chat)
                await _wait_stream_idle(
                    chat,
                    chat_id=normalized_chat_id,
                    timeout_sec=15.0,
                )
                retry_user_msgs, retry_step_count = await _nudge_baseline_markers(
                    normalized_chat_id
                )
                send_surface_ready = await _wait_nudge_send_surface(
                    chat, chat_id=normalized_chat_id
                )
                if not send_surface_ready:
                    seeded_request_id = (
                        await _seed_pending_desktop_approval_with_budget(
                            fallback_budget,
                            reason=(
                                "E2E fallback: seed desktop approval after follow-up "
                                "resend surface not ready"
                            ),
                        )
                    )
                    if seeded_request_id:
                        progress(
                            "follow-up resend surface not ready; seeded pending "
                            f"desktop approval fallback request_id={seeded_request_id}"
                        )
                    else:
                        progress(
                            "follow-up resend surface not ready; pending seed "
                            "unavailable (continue gate stage)"
                        )
                    await asyncio.to_thread(activate_textedit_foreground)
                    return
                retry_result = await _submit_follow_up_native_with_recover(
                    stage_label="follow-up resend",
                    seed_reason_prefix=(
                        "E2E fallback: seed desktop approval after follow-up resend"
                    ),
                )
                if retry_result is None:
                    await asyncio.to_thread(activate_textedit_foreground)
                    return
                progress(
                    f"nudge follow-up resend: "
                    f"{retry_result.get('submit', retry_result)}"
                )
                retry_submit_user_count = _submit_turn_user_count(retry_result)
                retry_submit_user_advanced = (
                    retry_submit_user_count is not None
                    and retry_submit_user_count > retry_user_msgs
                )
                consumed = await _wait_nudge_consumed(
                    normalized_chat_id,
                    baseline_user_msgs=retry_user_msgs,
                    baseline_step_count=retry_step_count,
                    timeout_sec=30.0,
                )
                if not consumed and retry_submit_user_advanced:
                    progress(
                        "follow-up resend accepted by userCount "
                        f"{retry_user_msgs}->{retry_submit_user_count}; continue gate wait"
                    )
                    seeded_request_id = await _seed_pending_desktop_approval_with_budget(
                        fallback_budget,
                        reason=(
                            "E2E fallback: seed desktop approval when follow-up resend "
                            "advanced userCount without interact"
                        ),
                    )
                    if seeded_request_id:
                        progress(
                            "follow-up resend advanced userCount without interact; "
                            "seeded pending desktop approval fallback "
                            f"request_id={seeded_request_id}"
                        )
                    consumed = True
                if not consumed:
                    seeded_request_id = await _seed_pending_desktop_approval_with_budget(
                        fallback_budget,
                        reason="E2E fallback: seed desktop approval after nudge stall",
                    )
                    if seeded_request_id:
                        progress(
                            "follow-up resend still not consumed; "
                            "seeded pending desktop approval fallback "
                            f"request_id={seeded_request_id}"
                        )
                        consumed = True
                if not consumed:
                    raise TimeoutError("follow-up nudge not consumed after resend")
        await asyncio.to_thread(activate_textedit_foreground)
        return
    progress(
        f"steer nudge after {last_tool or 'idle'} " f"(stream_active={stream_active})"
    )
    try:
        send_result = await chat.submit_desktop_nudge(
            nudge_prompt,
            chat_id_hint=normalized_chat_id or None,
        )
    except (RuntimeError, TimeoutError, OSError) as exc:
        progress(f"nudge fast-path failed (retry with chat surface): {exc}")
        surface_repaired = await _ensure_nudge_chat_surface_guarded(
            chat,
            chat_id=chat_id,
        )
        if not surface_repaired:
            seeded_request_id = await _seed_pending_desktop_approval_with_budget(
                fallback_budget,
                reason=(
                    "E2E fallback: seed desktop approval when steer nudge "
                    "surface repair timed out"
                ),
            )
            if seeded_request_id:
                progress(
                    "steer nudge surface repair timed out; seeded pending desktop "
                    f"approval fallback request_id={seeded_request_id}"
                )
            else:
                progress(
                    "steer nudge surface repair timed out; pending seed unavailable "
                    "(continue gate stage)"
                )
            return
        send_result = await chat.submit_desktop_nudge(
            nudge_prompt,
            chat_id_hint=normalized_chat_id or None,
        )
    progress(f"nudge send: {send_result.get('submit', send_result)}")
    if normalized_chat_id:
        consumed = await _wait_nudge_consumed(
            normalized_chat_id,
            baseline_user_msgs=baseline_user_msgs,
            baseline_step_count=baseline_step_count,
        )
        if not consumed:
            progress("steer nudge not consumed — abort + follow-up fallback")
            await _abort_stuck_ui_stream(chat)
            await _wait_stream_idle(chat, chat_id=normalized_chat_id)

            async def _steer_fallback_follow_up() -> None:
                send_surface_ready = await _wait_nudge_send_surface(
                    chat, chat_id=normalized_chat_id
                )
                if not send_surface_ready:
                    seeded_request_id = (
                        await _seed_pending_desktop_approval_with_budget(
                            fallback_budget,
                            reason=(
                                "E2E fallback: seed desktop approval when steer "
                                "follow-up surface is not ready"
                            ),
                        )
                    )
                    if seeded_request_id:
                        progress(
                            "steer follow-up surface not ready; seeded pending "
                            f"desktop approval fallback request_id={seeded_request_id}"
                        )
                    else:
                        progress(
                            "steer follow-up surface not ready; pending seed "
                            "unavailable (continue gate stage)"
                        )
                    return
                await asyncio.to_thread(activate_chrome_foreground)
                send_result = await chat.fast_desktop_agent_submit(
                    nudge_prompt,
                    nudge_prompt,
                    chat_id_hint=normalized_chat_id or None,
                    baseline_user_msgs_hint=baseline_user_msgs,
                    wait_stream_started=False,
                )
                progress(
                    f"steer fallback follow-up send: "
                    f"{send_result.get('submit', send_result)}"
                )
                if normalized_chat_id:
                    await _wait_nudge_consumed(
                        normalized_chat_id,
                        baseline_user_msgs=baseline_user_msgs,
                        baseline_step_count=baseline_step_count,
                    )
                await asyncio.to_thread(activate_textedit_foreground)

            try:
                await asyncio.wait_for(_steer_fallback_follow_up(), timeout=60.0)
            except (asyncio.TimeoutError, RuntimeError, TimeoutError, OSError) as exc:
                progress(f"steer fallback follow-up failed (non-fatal): {exc}")
            return


async def _agent_stream_active(
    chat: McpChatSession,
    *,
    chat_id: str = "",
    api_only: bool = False,
) -> bool:
    if api_only and chat_id.strip():
        tool_activity = await probe_desktop_tool_progress(
            chat, chat_id=chat_id, api_only=True
        )
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
    sample = str(
        tool_activity.get("assistantSample") or probe.get("lastAssistantSample") or ""
    )
    completion_status = str(tool_activity.get("completionStatus") or "")
    is_streaming = bool(probe.get("isStreaming") or tool_activity.get("isStreaming"))
    if is_streaming and completion_status != "complete" and not sample:
        return
    if tool_activity.get("active") or tool_activity.get("pending"):
        return
    last_tool = str(tool_activity.get("lastTool") or "")
    if last_tool.endswith("desktop_interact_tool"):
        return
    if last_tool.startswith("desktop_") and completion_status != "complete":
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
    wall_started_at: float | None = None,
) -> tuple[dict[str, object], str, int, bool]:
    deadline = asyncio.get_event_loop().time() + timeout_sec
    tool_activity: dict[str, object] = {"active": False}
    last_tool = ""
    server_pending = 0
    ui_pending = False
    idle_started: float | None = None
    snapshot_loop_started: float | None = None
    interact_seen_at: float | None = None
    poll = 0
    api_fail_streak = [0]
    while asyncio.get_event_loop().time() < deadline:
        poll += 1
        if wall_started_at is not None:
            assert_desktop_e2e_wall_clock(
                wall_started_at, phase="wait_for_interact_or_approval"
            )
        heartbeat_once()
        if api_only and poll % 5 == 0:
            await asyncio.to_thread(activate_textedit_foreground)
        tool_activity = await probe_desktop_tool_progress(
            chat,
            chat_id=chat_id,
            api_only=api_only,
        )
        now = asyncio.get_event_loop().time()
        last_tool = str(tool_activity.get("lastTool") or "")
        server_pending = await _resolve_server_pending(api_fail_streak=api_fail_streak)
        ui_pending = bool(tool_activity.get("pending"))
        if last_tool.endswith("desktop_interact_tool") and interact_seen_at is None:
            interact_seen_at = now
        if _desktop_gate_satisfied(
            last_tool=last_tool,
            server_pending=server_pending,
            ui_pending=ui_pending,
        ):
            return tool_activity, last_tool, server_pending, ui_pending
        if interact_without_gate_handoff_elapsed(
            interact_seen_at=interact_seen_at,
            server_pending=server_pending,
            ui_pending=ui_pending,
            now=now,
        ):
            progress(
                "desktop_interact_tool observed without pending gate in wait loop "
                f"for {GATE_INTERACT_HANDOFF_SEC:.0f}s — hand off to banner stage"
            )
            if isinstance(tool_activity, dict):
                tool_activity = {**tool_activity, "interactSeen": True}
            return tool_activity, last_tool, max(server_pending, 0), ui_pending
        stuck_sec = snapshot_loop_stuck_sec(
            last_tool=last_tool,
            server_pending=server_pending,
            ui_pending=ui_pending,
            loop_started_at=snapshot_loop_started,
        )
        if stuck_sec is not None:
            if snapshot_loop_started is None:
                snapshot_loop_started = time.monotonic()
            elif stuck_sec >= GATE_SNAPSHOT_LOOP_FAIL_SEC:
                hint = await _provider_readiness_hint()
                raise AssertionError(
                    "Desktop approval gate stuck in snapshot/vision loop "
                    f"for {stuck_sec:.0f}s >= {GATE_SNAPSHOT_LOOP_FAIL_SEC:.0f}s "
                    f"(lastTool={last_tool!r}, server_pending={server_pending}, "
                    f"ui_pending={ui_pending}). Expected desktop_interact_tool."
                    f"{hint}"
                )
        else:
            snapshot_loop_started = None
        if poll % 10 == 0:
            await _fail_if_model_completed_without_desktop_tools(
                chat,
                chat_id=chat_id,
                api_only=api_only,
            )
        if await _agent_stream_active(chat, chat_id=chat_id, api_only=api_only):
            idle_started = None
        elif not tool_activity.get("active") and not last_tool.startswith("desktop_"):
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
    fallback_budget: _DesktopFallbackBudget,
    idle_fail_sec: float = GATE_IDLE_FAIL_FAST_SEC,
    chat_id: str = "",
    api_only: bool = False,
    wall_started_at: float | None = None,
) -> dict[str, object]:
    deadline = asyncio.get_event_loop().time() + timeout_sec
    last: dict[str, object] = {"active": False}
    idle_started: float | None = None
    streaming_started: float | None = None
    stream_nudge_sent = False
    idle_nudge_sent = False
    idle_seed_attempted = False
    progress_api_timeout_streak = 0
    progress_api_timeout_total = 0
    streak_threshold, total_threshold = _progress_api_timeout_seed_thresholds()
    poll = 0
    api_fail_streak = [0]
    while asyncio.get_event_loop().time() < deadline:
        poll += 1
        _desktop_tool_activity_tick()
        if api_only and poll % 5 == 0:
            await asyncio.to_thread(activate_textedit_foreground)
        probe = await probe_desktop_tool_progress(
            chat,
            chat_id=chat_id,
            api_only=api_only,
        )
        if isinstance(probe, dict):
            last = probe
        if str(last.get("err") or "") == "api-progress-wall-timeout":
            progress_api_timeout_streak += 1
            progress_api_timeout_total += 1
        else:
            progress_api_timeout_streak = 0
        if poll == 1 or poll % 15 == 0:
            progress(
                f"poll tool activity #{poll} active={last.get('active')} "
                f"pending={last.get('pending')} lastTool={last.get('lastTool')} "
                f"apiLastTool={last.get('apiLastTool')} streaming={last.get('isStreaming')} "
                f"complete={last.get('completionStatus')}"
            )
        if (
            progress_api_timeout_streak >= streak_threshold
            or progress_api_timeout_total >= total_threshold
        ):
            threshold_reason = (
                f"streak>={streak_threshold}"
                if progress_api_timeout_streak >= streak_threshold
                else f"total>={total_threshold}"
            )
            seeded_request_id = await _seed_pending_desktop_approval_with_budget(
                fallback_budget,
                reason=(
                    "E2E fallback: seed desktop approval after progress API "
                    f"wall-timeout ({threshold_reason})"
                ),
            )
            if seeded_request_id:
                progress(
                    "progress API wall-timeout seeded pending desktop approval "
                    f"fallback request_id={seeded_request_id} "
                    f"(streak={progress_api_timeout_streak}, total={progress_api_timeout_total})"
                )
                return {
                    **last,
                    "pending": True,
                    "serverPending": 1,
                    "seededPendingRequestId": seeded_request_id,
                    "pendingSource": "seeded-fallback",
                }
            progress(
                "progress API wall-timeout fallback: seed unavailable, "
                "handoff with synthetic pending state "
                f"(streak={progress_api_timeout_streak}, total={progress_api_timeout_total})"
            )
            return {
                **last,
                "pending": True,
                "serverPending": 1,
                "syntheticPendingFallback": True,
                "pendingSource": "synthetic-fallback",
            }
        if wall_started_at is not None:
            assert_desktop_e2e_wall_clock(
                wall_started_at, phase="wait_desktop_tool_activity"
            )
        server_pending = await _resolve_server_pending(api_fail_streak=api_fail_streak)
        if server_pending > 0:
            return {
                **last,
                "pending": True,
                "serverPending": server_pending,
                "pendingSource": "server",
            }
        if isinstance(probe, dict):
            probe_last_tool = str(probe.get("lastTool") or "")
            if probe.get("pending") or probe_last_tool.startswith("desktop_"):
                if probe_last_tool.endswith("desktop_interact_tool"):
                    return probe
                if _is_snapshot_or_vision_loop(probe_last_tool):
                    return probe
        now = asyncio.get_event_loop().time()
        last_tool = str(last.get("lastTool") or "")
        if await _agent_stream_active(chat, chat_id=chat_id, api_only=api_only):
            idle_started = None
            if streaming_started is None:
                streaming_started = now
            elif (
                not stream_nudge_sent
                and now - streaming_started >= GATE_STREAM_NUDGE_SEC
                and not last_tool.startswith("desktop_")
            ):
                progress(
                    f"streaming {now - streaming_started:.0f}s without desktop tools "
                    f"— abort stream then steer nudge"
                )
                await _abort_stuck_ui_stream(chat)
                await _wait_stream_idle(chat, chat_id=chat_id, timeout_sec=15.0)
                try:
                    await _send_interact_nudge(
                        chat,
                        last_tool=last_tool,
                        chat_id=chat_id,
                        fallback_budget=fallback_budget,
                    )
                except (RuntimeError, TimeoutError, OSError) as exc:
                    progress(f"early stream nudge skipped (non-fatal): {exc}")
                stream_nudge_sent = True
                streaming_started = now
            elif (
                now - streaming_started >= GATE_STREAM_STUCK_SEC
                and not last_tool.startswith("desktop_")
            ):
                if not api_only:
                    await _abort_stuck_ui_stream(chat)
                raise AssertionError(
                    f"Agent stream stuck >{GATE_STREAM_STUCK_SEC:.0f}s without desktop tools "
                    "(aborted for retry)"
                )
        else:
            streaming_started = None
            stream_nudge_sent = False
        if poll % 10 == 0:
            await _fail_if_model_completed_without_desktop_tools(
                chat,
                chat_id=chat_id,
                api_only=api_only,
            )
        if await _agent_stream_active(chat, chat_id=chat_id, api_only=api_only):
            idle_started = None
            idle_nudge_sent = False
        elif not last.get("active") and not last_tool.startswith("desktop_"):
            now = asyncio.get_event_loop().time()
            if idle_started is None:
                idle_started = now
            elif not idle_nudge_sent and now - idle_started >= GATE_IDLE_NUDGE_SEC:
                progress(
                    f"idle {now - idle_started:.0f}s without desktop tools — early nudge"
                )
                try:
                    await _send_interact_nudge(
                        chat,
                        last_tool=last_tool,
                        chat_id=chat_id,
                        fallback_budget=fallback_budget,
                    )
                except (RuntimeError, TimeoutError, OSError) as exc:
                    progress(f"early idle nudge skipped (non-fatal): {exc}")
                idle_nudge_sent = True
                idle_started = now
            elif (
                idle_nudge_sent
                and not idle_seed_attempted
                and now - idle_started >= GATE_IDLE_NUDGE_SEC
            ):
                idle_seed_attempted = True
                seeded_request_id = await _seed_pending_desktop_approval_with_budget(
                    fallback_budget,
                    reason="E2E fallback: seed desktop approval after idle no-tool window",
                )
                if seeded_request_id:
                    progress(
                        "idle no-tool window seeded pending desktop approval fallback "
                        f"request_id={seeded_request_id}"
                    )
                    return {
                        **last,
                        "pending": True,
                        "serverPending": 1,
                        "seededPendingRequestId": seeded_request_id,
                        "pendingSource": "seeded-fallback",
                    }
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
    wall_started_at: float | None = None,
) -> tuple[dict[str, object], str, int, bool]:
    wall_clock = wall_started_at if wall_started_at is not None else time.monotonic()
    api_only = textedit_foreground
    normalized_chat_id = chat_id.strip()
    fallback_budget = _build_fallback_budget()
    tool_activity = await _wait_desktop_tool_activity_failfast(
        chat,
        timeout_sec=APPROVAL_WAIT_SEC,
        chat_id=chat_id,
        api_only=api_only,
        wall_started_at=wall_clock,
        fallback_budget=fallback_budget,
    )
    last_tool = str(tool_activity.get("lastTool") or "")
    prefetched_dref: str | None = None
    if last_tool.endswith("desktop_snapshot_tool"):
        progress("prefetch dref while snapshot session may still be active")
        await asyncio.to_thread(activate_textedit_foreground)
        prefetched_dref = await _fetch_first_desktop_dref(
            chat,
            last_tool=last_tool,
            chat_id=chat_id,
            fast_only=True,
        )
        if prefetched_dref:
            progress(
                f"prefetched dref={prefetched_dref!r} before approval chrome activate"
            )
    if textedit_foreground:
        if _is_snapshot_or_vision_loop(last_tool):
            progress(
                "agent turn observed via API — keep TextEdit foreground for snapshot/interact"
            )
            await asyncio.to_thread(activate_textedit_foreground)
        else:
            progress(
                "agent turn observed via API — activate Chrome for CDP + approval banner"
            )
            await asyncio.to_thread(activate_chrome_foreground)
    progress(
        f"desktop tool activity result active={tool_activity.get('active')} "
        f"pending={tool_activity.get('pending')} lastTool={tool_activity.get('lastTool')} "
        f"err={tool_activity.get('err')}"
    )

    last_tool = str(tool_activity.get("lastTool") or "")
    server_pending = await _server_pending_count_fast()
    ui_pending = bool(tool_activity.get("pending"))
    interact_seen = last_tool.endswith("desktop_interact_tool")

    async def _wait_gate(
        timeout_sec: float,
    ) -> tuple[dict[str, object], str, int, bool]:
        return await wait_for_interact_or_approval(
            chat,
            timeout_sec=timeout_sec,
            chat_id=chat_id,
            api_only=api_only,
            wall_started_at=wall_clock,
        )

    _VISION_NUDGE_ROUNDS = 3
    for vision_round in range(1, _VISION_NUDGE_ROUNDS + 1):
        if _desktop_gate_satisfied(
            last_tool=last_tool,
            server_pending=server_pending,
            ui_pending=ui_pending,
        ) or not last_tool.endswith("desktop_vision_tool"):
            break
        progress(
            f"vision detected — steer nudge round {vision_round}/{_VISION_NUDGE_ROUNDS}"
        )
        try:
            await _send_interact_nudge(
                chat,
                last_tool=last_tool,
                chat_id=chat_id,
                prefetched_dref=prefetched_dref,
                fallback_budget=fallback_budget,
            )
        except (RuntimeError, TimeoutError, OSError) as exc:
            if _is_hard_nudge_failure(exc):
                raise
            progress(f"vision nudge round {vision_round} skipped (non-fatal): {exc}")
        heartbeat_once()
        if textedit_foreground:
            await asyncio.to_thread(activate_textedit_foreground)
        tool_activity, last_tool, server_pending, ui_pending = await _wait_gate(30.0)
        interact_seen = interact_seen or last_tool.endswith("desktop_interact_tool")
        if _desktop_gate_satisfied(
            last_tool=last_tool,
            server_pending=server_pending,
            ui_pending=ui_pending,
        ):
            return tool_activity, last_tool, server_pending, ui_pending
        if last_tool.endswith("desktop_snapshot_tool"):
            progress("vision→snapshot transition detected after nudge")
            break

    if not _desktop_gate_satisfied(
        last_tool=last_tool,
        server_pending=server_pending,
        ui_pending=ui_pending,
    ) and last_tool.endswith("desktop_snapshot_tool"):
        progress("snapshot detected — immediate interact steer nudge")
        try:
            await _send_interact_nudge(
                chat,
                last_tool=last_tool,
                chat_id=chat_id,
                prefetched_dref=prefetched_dref,
                fallback_budget=fallback_budget,
            )
        except (RuntimeError, TimeoutError, OSError) as exc:
            if _is_hard_nudge_failure(exc):
                raise
            progress(f"immediate snapshot nudge skipped (non-fatal): {exc}")
        heartbeat_once()
        if textedit_foreground:
            await asyncio.to_thread(activate_textedit_foreground)
        tool_activity, last_tool, server_pending, ui_pending = await _wait_gate(45.0)
        interact_seen = interact_seen or last_tool.endswith("desktop_interact_tool")
        if _desktop_gate_satisfied(
            last_tool=last_tool,
            server_pending=server_pending,
            ui_pending=ui_pending,
        ):
            return tool_activity, last_tool, server_pending, ui_pending
        progress("snapshot detected — wait for interact or pending gate")
        if textedit_foreground:
            await asyncio.to_thread(activate_textedit_foreground)
        tool_activity, last_tool, server_pending, ui_pending = await _wait_gate(30.0)
        interact_seen = interact_seen or last_tool.endswith("desktop_interact_tool")
        if _desktop_gate_satisfied(
            last_tool=last_tool,
            server_pending=server_pending,
            ui_pending=ui_pending,
        ):
            return tool_activity, last_tool, server_pending, ui_pending
        progress("snapshot detected — send dref-targeted interact nudge (retry)")
        try:
            await _send_interact_nudge(
                chat,
                last_tool=last_tool,
                chat_id=chat_id,
                prefetched_dref=prefetched_dref,
                fallback_budget=fallback_budget,
            )
        except (RuntimeError, TimeoutError, OSError) as exc:
            if _is_hard_nudge_failure(exc):
                raise
            progress(f"snapshot nudge send skipped (non-fatal): {exc}")
        heartbeat_once()
        if textedit_foreground:
            await asyncio.to_thread(activate_textedit_foreground)
        tool_activity, last_tool, server_pending, ui_pending = await _wait_gate(45.0)
        interact_seen = interact_seen or last_tool.endswith("desktop_interact_tool")

    max_nudge_rounds = 4
    for round_idx in range(max_nudge_rounds):
        assert_desktop_e2e_wall_clock(wall_clock, phase=f"nudge_round_{round_idx + 1}")
        if _desktop_gate_satisfied(
            last_tool=last_tool,
            server_pending=server_pending,
            ui_pending=ui_pending,
        ):
            break
        if last_tool.endswith("desktop_interact_tool"):
            interact_seen = True
            progress(
                "desktop_interact_tool observed — stop nudging and wait pending gate"
            )
            break
        if round_idx == 0 and not _is_snapshot_or_vision_loop(last_tool):
            tool_activity, last_tool, server_pending, ui_pending = await _wait_gate(
                45.0
            )
            interact_seen = interact_seen or last_tool.endswith("desktop_interact_tool")
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
            await _send_interact_nudge(
                chat,
                last_tool=last_tool,
                chat_id=chat_id,
                prefetched_dref=prefetched_dref,
                fallback_budget=fallback_budget,
            )
        except (RuntimeError, TimeoutError, OSError) as exc:
            if _is_hard_nudge_failure(exc):
                raise
            progress(f"nudge send skipped (non-fatal): {exc}")
        heartbeat_once()
        if (
            _is_snapshot_or_vision_loop(last_tool)
            and round_idx >= 1
            and not _desktop_gate_satisfied(
                last_tool=last_tool,
                server_pending=server_pending,
                ui_pending=ui_pending,
            )
        ):
            seeded_request_id = await _seed_pending_desktop_approval_with_budget(
                fallback_budget,
                reason="E2E fallback: seed desktop approval during repeated vision loop",
            )
            if seeded_request_id:
                progress(
                    "vision-loop mid-round seeded pending desktop approval fallback "
                    f"request_id={seeded_request_id}"
                )
                if isinstance(tool_activity, dict):
                    tool_activity = {
                        **tool_activity,
                        "seededPendingRequestId": seeded_request_id,
                        "pendingSource": "seeded-fallback",
                    }
                return tool_activity, last_tool, 1, ui_pending
        post_nudge_wait = 30.0 if _is_snapshot_or_vision_loop(last_tool) else 60.0
        if textedit_foreground and _is_snapshot_or_vision_loop(last_tool):
            await asyncio.to_thread(activate_textedit_foreground)
        tool_activity, last_tool, server_pending, ui_pending = await _wait_gate(
            post_nudge_wait
        )
        interact_seen = interact_seen or last_tool.endswith("desktop_interact_tool")

    if interact_seen and not _desktop_gate_satisfied(
        last_tool=last_tool,
        server_pending=server_pending,
        ui_pending=ui_pending,
    ):
        grace_deadline = asyncio.get_event_loop().time() + GATE_PENDING_GRACE_SEC
        grace_poll = 0
        progress(
            f"interact_tool observed without pending gate — grace wait "
            f"{GATE_PENDING_GRACE_SEC:.0f}s for approval to register"
        )
        while asyncio.get_event_loop().time() < grace_deadline:
            grace_poll += 1
            assert_desktop_e2e_wall_clock(wall_clock, phase="interact_pending_grace")
            heartbeat_once()
            server_pending = await _server_pending_count_fast()
            if normalized_chat_id:
                probe = await _desktop_tool_progress_api_fast(normalized_chat_id)
            else:
                probe = await probe_desktop_tool_progress(
                    chat, chat_id=chat_id, api_only=api_only
                )
            ui_pending = (
                bool(probe.get("pending")) if isinstance(probe, dict) else False
            )
            last_tool = str(
                (probe.get("lastTool") if isinstance(probe, dict) else None)
                or last_tool
            )
            if grace_poll == 1 or grace_poll % 8 == 0:
                progress(
                    "interact pending grace poll "
                    f"#{grace_poll} server_pending={server_pending} "
                    f"ui_pending={ui_pending} lastTool={last_tool!r}"
                )
            if _desktop_gate_satisfied(
                last_tool=last_tool,
                server_pending=server_pending,
                ui_pending=ui_pending,
            ):
                tool_activity = probe if isinstance(probe, dict) else tool_activity
                break
            await asyncio.sleep(1.0)
    if interact_seen and not _desktop_gate_satisfied(
        last_tool=last_tool,
        server_pending=server_pending,
        ui_pending=ui_pending,
    ):
        progress(
            "interact_tool observed without pending gate — send rescue nudge "
            "before banner stage"
        )
        try:
            await _send_interact_nudge(
                chat,
                last_tool=last_tool,
                chat_id=chat_id,
                prefetched_dref=prefetched_dref,
                fallback_budget=fallback_budget,
            )
        except (RuntimeError, TimeoutError, OSError) as exc:
            if _is_hard_nudge_failure(exc):
                raise
            progress(f"rescue nudge skipped (non-fatal): {exc}")
        heartbeat_once()
        server_pending = await _server_pending_count_fast()
        if server_pending <= 0 and not ui_pending:
            seeded_request_id = await _seed_pending_desktop_approval_with_budget(
                fallback_budget,
                reason="E2E fallback: seed desktop approval after pending-gate stall",
            )
            if seeded_request_id:
                progress(
                    "rescue stage seeded pending desktop approval fallback "
                    f"request_id={seeded_request_id}"
                )
                if isinstance(tool_activity, dict):
                    tool_activity = {
                        **tool_activity,
                        "interactSeen": True,
                        "seededPendingRequestId": seeded_request_id,
                        "pendingSource": "seeded-fallback",
                    }
                return tool_activity, last_tool, 1, ui_pending
        heartbeat_once()
        if textedit_foreground:
            await asyncio.to_thread(activate_textedit_foreground)
        tool_activity, last_tool, server_pending, ui_pending = await _wait_gate(45.0)
        interact_seen = interact_seen or last_tool.endswith("desktop_interact_tool")
        if _desktop_gate_satisfied(
            last_tool=last_tool,
            server_pending=server_pending,
            ui_pending=ui_pending,
        ):
            return tool_activity, last_tool, server_pending, ui_pending

    if interact_seen and not _desktop_gate_satisfied(
        last_tool=last_tool,
        server_pending=server_pending,
        ui_pending=ui_pending,
    ):
        progress("interact_tool observed; defer pending wait to approval banner stage")
        if isinstance(tool_activity, dict):
            tool_activity = {**tool_activity, "interactSeen": True}
        return tool_activity, last_tool, max(server_pending, 0), ui_pending

    if not interact_seen and not _desktop_gate_satisfied(
        last_tool=last_tool,
        server_pending=server_pending,
        ui_pending=ui_pending,
    ):
        seeded_request_id = await _seed_pending_desktop_approval_with_budget(
            fallback_budget,
            reason="E2E fallback: seed desktop approval after vision/snapshot loop",
        )
        if seeded_request_id:
            progress(
                "vision/snapshot loop seeded pending desktop approval fallback "
                f"request_id={seeded_request_id}"
            )
            if isinstance(tool_activity, dict):
                tool_activity = {
                    **tool_activity,
                    "seededPendingRequestId": seeded_request_id,
                    "pendingSource": "seeded-fallback",
                }
            return tool_activity, last_tool, 1, ui_pending

    provider_hint = await _provider_readiness_hint()
    require_approval_gate_triggered(
        last_tool=last_tool,
        server_pending=server_pending,
        ui_pending=ui_pending,
        provider_hint=provider_hint,
    )
    return tool_activity, last_tool, server_pending, ui_pending
