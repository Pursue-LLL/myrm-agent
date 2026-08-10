"""Chat shell bootstrap and hydration workflow."""

from __future__ import annotations

import asyncio
import os
import time

from cdp_chat_support import (
    DISMISS_MODALS_JS,
    MODEL_PROBE_JS,
    PAGE_PROBE_JS,
    RESET_CHAT_JS,
    _api_provider_ready,
    chat_id_from_path,
    e2e_api_base_inject_js,
    e2e_api_base_persist_source,
    e2e_runtime_bootstrap_apply_js,
    get_e2e_ui_url,
    shpoib_parallel_shell_timeout_sec,
    shpoib_shell_wait_slice_cap,
)
from cdp_chat_transport import CdpChatTransport
from dev_gate_contract import EvaluateIntent

_SHELL_PROBE_RECV_TIMEOUT_SEC = 15.0


def _signoff_bridge_hydrate_cap_sec() -> float:
    """R225: scale bridge/shared-ui hydrate slice under parallel signoff (v149 @9 leases)."""
    cap = 90.0
    if os.environ.get("E2E_SIGNOFF", "").strip() != "1":
        return cap
    try:
        from dev_gate_contract import _parallel_signoff_pressure_peers

        peers = _parallel_signoff_pressure_peers()
        if peers >= 2:
            return min(180.0, 90.0 + peers * 10.0)
    except ImportError:
        pass
    return cap
_SHELL_PROBE_PROGRESS_INTERVAL_SEC = 30.0
_SHELL_PROBE_POLL_HARD_TIMEOUT_SEC = 75.0


def _parallel_shpoib_shell_timeout(timeout_sec: float) -> float:
    return shpoib_parallel_shell_timeout_sec(timeout_sec)


def split_bootstrap_deadlines(
    timeout_sec: float,
    *,
    now: float | None = None,
) -> tuple[float, float]:
    """Return ``(shell_deadline, bridge_deadline)`` with bridge hydrate reserve.

    Parallel SHPOIB scales the outer bootstrap wall for shell mux contention but
    must not consume the shared UI session contract budget (RESET_GLOBALS…).
    """
    from dev_gate_contract import (
        E2E_BOOTSTRAP_BRIDGE_HYDRATE_RESERVE_SEC,
        E2E_BOOTSTRAP_SHELL_MIN_SEC,
    )

    start = time.monotonic() if now is None else now
    total_deadline = start + timeout_sec
    reserve = float(E2E_BOOTSTRAP_BRIDGE_HYDRATE_RESERVE_SEC)
    shell_budget = max(float(E2E_BOOTSTRAP_SHELL_MIN_SEC), timeout_sec - reserve)
    shell_deadline = start + shell_budget
    return shell_deadline, total_deadline


def _bootstrap_hot_path_reused() -> bool:
    return os.environ.get("MYRM_E2E_BOOTSTRAP_HOT_PATH", "").strip() == "reused"


def _bootstrap_hot_path_fast() -> bool:
    if os.environ.get("MYRM_E2E_BOOTSTRAP_HOT_PATH", "").strip() == "reused":
        return True
    return (
        os.environ.get("MYRM_E2E_PHASE_C_BURST_SKIP_ATTACH", "").strip() == "1"
        and os.environ.get("MYRM_E2E_BOOTSTRAP_HOT_PATH", "").strip() == "fast_create"
    )


async def _warm_shell_bootstrap_probe(chat: CdpChatTransport) -> dict[str, object] | None:
    """Return PAGE_PROBE when warm/presealed shell is already chat-ready."""
    if not _bootstrap_hot_path_fast():
        return None
    probe_raw = await chat.evaluate(
        PAGE_PROBE_JS,
        intent=EvaluateIntent.SYNC_PROBE,
    )
    if not isinstance(probe_raw, dict):
        return None
    if (
        probe_raw.get("hasInput") is True
        and probe_raw.get("hasBridge") is True
        and probe_raw.get("clientHydrated") is True
        and probe_raw.get("skeleton") is not True
        and probe_raw.get("hasLayout") is True
    ):
        return probe_raw
    return None


def _shell_probe_stall_cap_sec() -> float:
    from dev_gate_contract import SHELL_PROBE_STALL_FAIL_FAST_SEC

    cap = float(SHELL_PROBE_STALL_FAIL_FAST_SEC)
    # Shared-hot desktop chrome_e2e can require longer mux reclaim/hydration.
    if os.environ.get("MYRM_E2E_SHARED_HOT", "").strip() == "1":
        cap = max(cap, 180.0)
    if os.environ.get("E2E_SIGNOFF", "").strip() == "1":
        cap = max(cap, 180.0)
        try:
            from chrome_mcp_client import _parallel_mux_peer_count

            cap = min(cap + _parallel_mux_peer_count() * 12.0, 240.0)
        except Exception:
            pass
    return cap


def _shell_probe_ready(probe: dict[str, object]) -> bool:
    if probe.get("hasInput"):
        return True
    if probe.get("skeleton"):
        return False
    return bool(
        probe.get("hasBridge")
        and probe.get("clientHydrated")
        and probe.get("hasLayout")
    )


def _blank_chat_shell_probe(probe: dict[str, object]) -> bool:
    """True when shared :3000 tab lost chat shell under parallel UI hydrate."""
    if probe.get("skeleton"):
        return False
    if probe.get("hasInput") or probe.get("hasBridge"):
        return False
    path = str(probe.get("path") or "/").strip() or "/"
    return path == "/"


def _bootstrap_shell_heal_polls(poll: int) -> bool:
    return poll in {1, 8, 20, 35, 50, 65}


def _bootstrap_shell_heal_wall_cap_sec(parallel_active: int) -> float:
    """R179: fail-fast shell heal under parallel mux so soak mux_retry can recover."""
    load = max(0, int(parallel_active))
    if load >= 4:
        return 75.0
    if load >= 2:
        return 90.0
    return 120.0


class CdpChatBootstrap(CdpChatTransport):
    _e2e_api_base_bound: bool = False
    _shared_ui_session_contract_applied: bool = False
    _bootstrap_started_monotonic: float | None = None
    # Session SSOT: hydrate re-entry must not reset shell-layout stall clock (R51).
    _shell_layout_wait_started: float | None = None
    # R73-A: session-level stall clock — never reset on mux recover retry.
    _shell_session_started: float | None = None
    _shell_skeleton_since: float | None = None
    _shell_hydrate_depth: int = 0

    def _mark_bootstrap_started(self) -> None:
        if self._bootstrap_started_monotonic is None:
            self._bootstrap_started_monotonic = time.monotonic()

    def _reset_shell_layout_wait_clock(self) -> None:
        """Fresh shell-layout poll budget after page reopen (not session stall clock)."""
        self._shell_layout_wait_started = None
        self._last_shell_probe_log_sec = -1

    def _reset_shell_session_clock(self) -> None:
        """Fresh shell stall budget for a new approval attempt or post-retry heal."""
        self._shell_session_started = None
        self._shell_skeleton_since = None
        self._reset_shell_layout_wait_clock()

    def _ensure_shell_session_started(self) -> float:
        if self._shell_session_started is None:
            self._shell_session_started = time.monotonic()
        return self._shell_session_started

    def _check_skeleton_stall(self, probe: dict[str, object], *, phase: str) -> None:
        """Fail-fast when UI stays skeleton/blank without progress (R73-A)."""
        from dev_gate_contract import (
            E2E_SHELL_SKELETON_STALL_TOKEN,
            shell_probe_stall_fail_fast_effective_sec,
        )

        skeleton = bool(probe.get("skeleton"))
        blank_shell = not probe.get("hasInput") and not _shell_probe_ready(probe)
        if not skeleton and not blank_shell:
            self._shell_skeleton_since = None
            return

        now = time.monotonic()
        if self._shell_skeleton_since is None:
            self._shell_skeleton_since = now
        skeleton_elapsed = now - self._shell_skeleton_since
        session_elapsed = now - self._ensure_shell_session_started()
        cap = shell_probe_stall_fail_fast_effective_sec()
        if skeleton_elapsed >= cap or session_elapsed >= cap:
            raise RuntimeError(
                f"{E2E_SHELL_SKELETON_STALL_TOKEN}: phase={phase} "
                f"skeleton_elapsed={skeleton_elapsed:.1f}s "
                f"session_elapsed={session_elapsed:.1f}s cap={int(cap)}s "
                f"probe={probe}"
            )

    def _check_shell_layout_stall_cap(self) -> None:
        from dev_gate_contract import (
            MUX_RECLAIM_STALL_TOKEN,
        )

        started = self._shell_layout_wait_started
        if started is None:
            return
        elapsed = time.monotonic() - started
        session_elapsed = time.monotonic() - self._ensure_shell_session_started()
        stall_cap = _shell_probe_stall_cap_sec()
        if elapsed >= stall_cap or session_elapsed >= stall_cap:
            raise RuntimeError(
                f"{MUX_RECLAIM_STALL_TOKEN}: wait_shell_layout stalled "
                f"{elapsed:.1f}s (cap={int(stall_cap)}s); recover mux and retry"
            )

    def _check_bootstrap_stall_fail_fast(self, *, phase: str) -> None:
        try:
            from e2e_orchestrator import assert_wall_budget

            assert_wall_budget(phase)
            return
        except ImportError:
            pass
        from dev_gate_contract import (
            LIVE_SINGLE_TEST_WALL_CLOCK_SEC,
        )

        if self._bootstrap_started_monotonic is None:
            return
        elapsed = time.monotonic() - self._bootstrap_started_monotonic
        bootstrap_cap = _shell_probe_stall_cap_sec()
        if phase in {"bootstrap_shell", "ensure_chat_surface", "wait_shell_layout"}:
            cap = bootstrap_cap
        else:
            cap = float(LIVE_SINGLE_TEST_WALL_CLOCK_SEC)
        if elapsed >= cap:
            import sys

            print(
                f"E2E_BOOTSTRAP_STALL_FAIL_FAST: elapsed={int(elapsed)}s "
                f"cap={int(cap)}s phase={phase}",
                file=sys.stderr,
                flush=True,
            )
            raise TimeoutError(
                f"E2E_BOOTSTRAP_STALL_FAIL_FAST after {int(elapsed)}s "
                f"(phase={phase})"
            )

    def _shell_probe_progress(self, *, polls: int, started: float, phase: str) -> None:
        import sys

        try:
            from e2e_session_lifecycle import touch_wall_progress

            touch_wall_progress(current_node=phase)
        except ImportError:
            pass

        elapsed = int(time.monotonic() - started)
        last_logged = getattr(self, "_last_shell_probe_log_sec", -1)
        if polls == 1 or (
            elapsed > 0
            and elapsed % _SHELL_PROBE_PROGRESS_INTERVAL_SEC == 0
            and elapsed != last_logged
        ):
            self._last_shell_probe_log_sec = elapsed
            print(
                f"E2E_SHELL_PROBE_PROGRESS: phase={phase} polls={polls} elapsed={elapsed}s",
                file=sys.stderr,
                flush=True,
            )
        self._check_bootstrap_stall_fail_fast(phase=phase)

    async def _shared_ui_burst(self, operation: str, action):
        from e2e_shared_ui_hydrate import async_shared_ui_hydrate_burst

        async with async_shared_ui_hydrate_burst():
            return await action

    async def ensure_e2e_api_base_binding(self) -> None:
        """Register persistent new-document hook once + immediate inject for SHPOIB private pools."""
        source = e2e_api_base_persist_source()
        if not source:
            return
        if not self._e2e_api_base_bound:
            await self.cdp("Page.addScriptToEvaluateOnNewDocument", {"source": source})
            self._e2e_api_base_bound = True
        bootstrap_js = e2e_runtime_bootstrap_apply_js()
        if bootstrap_js is not None:
            if getattr(self, "_e2e_runtime_bootstrapped", False):
                await self.evaluate(
                    e2e_api_base_inject_js(),
                    intent=EvaluateIntent.ROUTE_ATTACH,
                )
                return
            result = await self.evaluate(
                bootstrap_js,
                intent=EvaluateIntent.ROUTE_ATTACH,
            )
            if isinstance(result, dict) and result.get("ok") is True:
                self._e2e_runtime_bootstrapped = True
                return
            await self.evaluate(
                e2e_api_base_inject_js(),
                intent=EvaluateIntent.ROUTE_ATTACH,
            )
            return
        await self.evaluate(
            e2e_api_base_inject_js(),
            intent=EvaluateIntent.ROUTE_ATTACH,
        )

    async def bootstrap(
        self,
        base_url: str,
        *,
        timeout_sec: float = 180.0,
        navigate: bool = False,
    ) -> dict[str, object]:
        from e2e_session_lifecycle import (  # noqa: PLC0415
            begin_bootstrap_phase,
            provider_readiness_gate_sync,
        )

        begin_bootstrap_phase(phase_label="cdp_bootstrap")
        skip_provider_gate = (
            os.environ.get("E2E_SIGNOFF", "").strip() == "1"
            and os.environ.get("MYRM_E2E_PHASE_C_BURST_SKIP_ATTACH", "").strip() == "1"
        )
        if not skip_provider_gate:
            await asyncio.to_thread(provider_readiness_gate_sync)
        timeout_sec = _parallel_shpoib_shell_timeout(timeout_sec)
        shell_deadline, bridge_deadline = split_bootstrap_deadlines(timeout_sec)
        self._reset_shell_layout_wait_clock()
        self._mark_bootstrap_started()
        last = await self._bootstrap_shell_ready_phase(
            base_url,
            deadline=shell_deadline,
            navigate=navigate,
        )
        return await self._bootstrap_bridge_hydrate_phase(
            last, deadline=bridge_deadline
        )

    async def _bootstrap_shell_ready_phase(
        self,
        base_url: str,
        *,
        deadline: float,
        navigate: bool,
    ) -> dict[str, object]:
        import sys

        print(
            "E2E_BOOTSTRAP_SHELL_START: phase=bootstrap_shell",
            file=sys.stderr,
            flush=True,
        )
        last: dict[str, object] = {}
        cdp_cap = min(30.0, max(5.0, deadline - time.monotonic()))
        await asyncio.wait_for(self.cdp("Runtime.enable"), timeout=cdp_cap)
        await asyncio.wait_for(self.cdp("Page.enable"), timeout=cdp_cap)
        await self.ensure_e2e_api_base_binding()
        if navigate:
            probe = await self.evaluate(
                PAGE_PROBE_JS,
                intent=EvaluateIntent.SYNC_PROBE,
            )
            if not (
                isinstance(probe, dict)
                and probe.get("hasInput")
                and not probe.get("skeleton")
            ):
                await self._shared_ui_burst(
                    "navigate",
                    self.cdp(
                        "Page.navigate",
                        {"url": base_url.rstrip("/") + "/"},
                        recv_timeout=120.0,
                    ),
                )
                await asyncio.sleep(2)
        else:
            reused_probe = await _warm_shell_bootstrap_probe(self)
            if reused_probe is not None:
                import sys

                print(
                    "E2E_BOOTSTRAP_SHELL_FASTPATH: reused warm shell ready",
                    file=sys.stderr,
                    flush=True,
                )
                return reused_probe
            await asyncio.sleep(2)
        if os.environ.get("MYRM_E2E_SHPOIB", "").strip() == "1":
            remaining_timeout = max(5.0, deadline - time.monotonic())
            return await self._wait_shell_ready_inner(
                timeout_sec=remaining_timeout,
                require_bridge=False,
            )
        probe_started = time.monotonic()
        if self._shell_layout_wait_started is None:
            self._shell_layout_wait_started = probe_started
        return await self._wait_shell_layout_ready(deadline=deadline)

    async def _bootstrap_bridge_hydrate_phase(
        self,
        last: dict[str, object],
        *,
        deadline: float,
    ) -> dict[str, object]:
        bridge_timeout = max(0.0, deadline - time.monotonic())
        if bridge_timeout <= 0.0:
            from e2e_session_lifecycle import current_phase, remaining_wall_sec

            remaining = remaining_wall_sec()
            if current_phase() == "bootstrap" and remaining > 20.0:
                bridge_cap = _signoff_bridge_hydrate_cap_sec()
                deadline = time.monotonic() + min(bridge_cap, remaining - 5.0)
                bridge_timeout = max(0.0, deadline - time.monotonic())
        if bridge_timeout > 0:
            reused_probe = await _warm_shell_bootstrap_probe(self)
            if reused_probe is not None:
                import sys

                print(
                    "E2E_BOOTSTRAP_HOT_PATH_FASTPATH: skip bridge hydrate (reused warm shell)",
                    file=sys.stderr,
                    flush=True,
                )
                last = reused_probe
            else:
                hydrate_cap = _signoff_bridge_hydrate_cap_sec()
                await self.ensure_dev_bridge(timeout_sec=min(bridge_timeout, hydrate_cap))
                hydrate_timeout = max(0.0, deadline - time.monotonic())
                if hydrate_timeout > 0:
                    await self._wait_react_hydration(timeout_sec=hydrate_timeout)
                provider_timeout = max(0.0, deadline - time.monotonic())
                if provider_timeout > 0:
                    await self._wait_providers_hydrated(
                        timeout_sec=min(provider_timeout, hydrate_cap)
                    )
                probe = await self.evaluate(
                    PAGE_PROBE_JS,
                    intent=EvaluateIntent.SYNC_PROBE,
                )
                if isinstance(probe, dict):
                    last = probe
                else:
                    last = {"probeError": probe}
        await self._maybe_apply_shared_ui_session_contract(deadline=deadline)
        from e2e_session_lifecycle import complete_bootstrap_phase

        complete_bootstrap_phase(phase_label="post_cdp_bootstrap")
        return last

    async def _maybe_apply_shared_ui_session_contract(
        self,
        *,
        deadline: float | None = None,
    ) -> None:
        from e2e_shared_ui_session import maybe_apply_shared_ui_session_contract

        result = await maybe_apply_shared_ui_session_contract(
            self,
            timeout_sec=_signoff_bridge_hydrate_cap_sec(),
            deadline=deadline,
        )
        if result is not None and result.get("skipped") is not True:
            self._shared_ui_session_contract_applied = True

    async def _reapply_shared_ui_after_new_chat(
        self,
        *,
        deadline: float | None = None,
    ) -> None:
        from e2e_shared_ui_session import reapply_shared_ui_session_after_new_chat

        await reapply_shared_ui_session_after_new_chat(self, deadline=deadline)

    async def _bootstrap_inner(
        self,
        base_url: str,
        *,
        timeout_sec: float = 180.0,
        navigate: bool = False,
    ) -> dict[str, object]:
        """Legacy single-phase bootstrap (tests); prefer ``bootstrap``."""
        timeout_sec = _parallel_shpoib_shell_timeout(timeout_sec)
        shell_deadline, bridge_deadline = split_bootstrap_deadlines(timeout_sec)
        last = await self._bootstrap_shell_ready_phase(
            base_url,
            deadline=shell_deadline,
            navigate=navigate,
        )
        return await self._bootstrap_bridge_hydrate_phase(
            last, deadline=bridge_deadline
        )

    async def wait_shell_ready(
        self,
        *,
        timeout_sec: float = 120.0,
        require_bridge: bool = True,
    ) -> dict[str, object]:
        """Lightweight shell wait for MCP pages already navigated to the app URL."""
        from dev_gate_contract import MUX_RECLAIM_STALL_TOKEN

        timeout_sec = _parallel_shpoib_shell_timeout(timeout_sec)
        self._reset_shell_layout_wait_clock()
        self._mark_bootstrap_started()
        # R53/R67: parallel SHPOIB uses inner poll — nested wait_shell_layout mux-deadlocks.
        if require_bridge and os.environ.get("MYRM_E2E_SHPOIB", "").strip() == "1":
            return await self._wait_shell_ready_inner(
                timeout_sec=timeout_sec,
                require_bridge=True,
            )
        for attempt in range(2):
            deadline = time.monotonic() + timeout_sec
            try:
                if require_bridge:
                    last = await self._wait_shell_layout_ready(deadline=deadline)
                    return await self._wait_shell_bridge_finish(
                        last,
                        deadline=deadline,
                        require_bridge=True,
                    )
                return await self._wait_shell_ready_inner(
                    timeout_sec=max(0.0, deadline - time.monotonic()),
                    require_bridge=require_bridge,
                )
            except RuntimeError as exc:
                if MUX_RECLAIM_STALL_TOKEN not in str(exc) or attempt >= 1:
                    raise
                await self._recover_shell_probe_mux(0)
                client = getattr(self, "_client", None)
                abandon = getattr(client, "abandon_inflight_requests", None)
                if callable(abandon):
                    abandon()
                await asyncio.sleep(1.0)

    async def _recover_shell_probe_mux(self, mux_recover_attempts: int) -> int:
        from dev_gate_contract import MUX_RECLAIM_STALL_TOKEN

        client = getattr(self, "_client", None)
        if client is not None and mux_recover_attempts < 1:
            loop = asyncio.get_running_loop()
            try:
                await asyncio.wait_for(
                    loop.run_in_executor(
                        client.mux_reset_executor(),
                        client.reset_after_orphan,
                    ),
                    timeout=45.0,
                )
            except TimeoutError as exc:
                client.discard_mux_reset_executor()
                raise RuntimeError(
                    f"{MUX_RECLAIM_STALL_TOKEN}: reset_after_orphan timed out after 45s"
                ) from exc
            return mux_recover_attempts + 1
        return mux_recover_attempts

    async def _wait_shell_layout_ready(self, *, deadline: float) -> dict[str, object]:
        from dev_gate_contract import (
            MUX_PAGE_RECLAIM_HARD_TIMEOUT_SEC,
            MUX_RECLAIM_STALL_TOKEN,
        )

        last: dict[str, object] = {}
        polls = 0
        if self._shell_layout_wait_started is None:
            self._shell_layout_wait_started = time.monotonic()
        layout_wait_started = self._shell_layout_wait_started
        probe_started = layout_wait_started
        mux_recover_attempts = 0
        stall_cap = _shell_probe_stall_cap_sec()
        per_eval_cap = min(30.0, stall_cap)
        eval_wall_sec = min(
            _SHELL_PROBE_RECV_TIMEOUT_SEC + 25.0,
            _SHELL_PROBE_RECV_TIMEOUT_SEC
            + float(MUX_PAGE_RECLAIM_HARD_TIMEOUT_SEC)
            + 15.0,
        )
        orphan_eval_task: asyncio.Task[object] | None = None
        while time.monotonic() < deadline:
            polls += 1
            self._shell_probe_progress(
                polls=polls, started=probe_started, phase="wait_shell_layout"
            )
            elapsed_total = time.monotonic() - layout_wait_started
            if elapsed_total >= stall_cap:
                raise RuntimeError(
                    f"{MUX_RECLAIM_STALL_TOKEN}: wait_shell_layout stalled "
                    f"{elapsed_total:.1f}s (cap={int(stall_cap)}s); "
                    "recover mux and retry"
                )
            self._check_shell_layout_stall_cap()

            async def _run_one_shell_layout_poll() -> dict[str, object]:
                nonlocal orphan_eval_task
                if orphan_eval_task is not None and not orphan_eval_task.done():
                    await asyncio.wait({orphan_eval_task}, timeout=2.0)
                    if not orphan_eval_task.done():
                        return {
                            "probeError": "evaluate_timeout",
                            "_mux_recover": True,
                        }
                eval_timeout = min(
                    per_eval_cap,
                    eval_wall_sec,
                    max(5.0, deadline - time.monotonic()),
                )
                evaluate_task = asyncio.create_task(
                    self.evaluate(
                        PAGE_PROBE_JS,
                        intent=EvaluateIntent.SYNC_PROBE,
                    )
                )
                done, pending = await asyncio.wait(
                    {evaluate_task},
                    timeout=eval_timeout,
                )
                if pending:
                    orphan_eval_task = evaluate_task
                    return {
                        "probeError": "evaluate_timeout",
                        "_mux_recover": True,
                    }
                orphan_eval_task = None
                try:
                    poll_state = evaluate_task.result()
                except TimeoutError:
                    return {
                        "probeError": "evaluate_timeout",
                        "_mux_recover": True,
                    }
                return (
                    poll_state
                    if isinstance(poll_state, dict)
                    else {"probeError": poll_state}
                )

            remaining_stall = max(0.05, stall_cap - elapsed_total)
            poll_hard = min(
                _SHELL_PROBE_POLL_HARD_TIMEOUT_SEC,
                remaining_stall,
                max(0.05, deadline - time.monotonic()),
            )
            poll_timed_out = False
            try:
                state = await asyncio.wait_for(
                    _run_one_shell_layout_poll(),
                    timeout=poll_hard,
                )
            except TimeoutError:
                poll_timed_out = True
                reset_client = getattr(self, "_client", None)
                if reset_client is not None:
                    reset_client.discard_mux_reset_executor()
                state = {
                    "probeError": "evaluate_timeout",
                    "_mux_recover": True,
                }
            except RuntimeError as exc:
                message = str(exc)
                if MUX_RECLAIM_STALL_TOKEN in message:
                    if mux_recover_attempts < 1:
                        mux_recover_attempts = await self._recover_shell_probe_mux(
                            mux_recover_attempts
                        )
                        continue
                    raise
                if any(
                    token in message
                    for token in ("Target closed", "No page found", "detached Frame")
                ):
                    await asyncio.sleep(1)
                    continue
                raise
            needs_mux_recover = bool(
                poll_timed_out or state.get("_mux_recover") is True
            )
            if isinstance(state, dict):
                state.pop("_mux_recover", None)
            if needs_mux_recover:
                mux_recover_attempts = await self._recover_shell_probe_mux(
                    mux_recover_attempts
                )
                elapsed_after = time.monotonic() - layout_wait_started
                if mux_recover_attempts >= 1 and elapsed_after >= stall_cap:
                    raise RuntimeError(
                        f"{MUX_RECLAIM_STALL_TOKEN}: wait_shell_layout evaluate "
                        f"timed out after mux recover ({elapsed_after:.1f}s "
                        f"cap={int(stall_cap)}s)"
                    )
                if poll_timed_out and elapsed_after >= stall_cap:
                    raise RuntimeError(
                        f"{MUX_RECLAIM_STALL_TOKEN}: wait_shell_layout poll hard "
                        f"timeout {elapsed_after:.1f}s (cap={int(stall_cap)}s)"
                    )
            elif (
                isinstance(state, dict)
                and state.get("probeError") == "evaluate_timeout"
            ):
                elapsed_after = time.monotonic() - layout_wait_started
                if mux_recover_attempts >= 1 and elapsed_after >= stall_cap:
                    raise RuntimeError(
                        f"{MUX_RECLAIM_STALL_TOKEN}: wait_shell_layout evaluate "
                        f"timed out after mux recover ({elapsed_after:.1f}s "
                        f"cap={int(stall_cap)}s)"
                    )
            last = state if isinstance(state, dict) else {"probeError": state}
            self._check_skeleton_stall(last, phase="wait_shell_layout")
            if (
                last.get("probeError") == "evaluate_timeout"
                and polls >= 25
                and polls % 25 == 0
            ):
                try:
                    await self._reload_chat_shell_burst()
                except (RuntimeError, TimeoutError):
                    pass
            if not _shell_probe_ready(last):
                path = str(last.get("path") or "")
                probe_timed_out = last.get("probeError") == "evaluate_timeout"
                stale_home = (
                    probe_timed_out
                    or path in ("", "/", "blank", "about:blank")
                    or not last.get("hasLayout")
                )
                hydrate_polls = {2, 4, 8, 16, 24, 48, 72, 96, 120}
                if (
                    stale_home
                    and polls in hydrate_polls
                    and self._shell_hydrate_depth == 0
                ):
                    ui_base = (
                        getattr(self, "_base_url", None) or get_e2e_ui_url()
                    ).rstrip("/")
                    hydrate_deadline = min(deadline, time.monotonic() + 120.0)
                    try:
                        await self._hydrate_chat_home_surface(
                            ui_base,
                            deadline=hydrate_deadline,
                        )
                    except (RuntimeError, TimeoutError):
                        try:
                            await self._reload_chat_shell_burst()
                        except (RuntimeError, TimeoutError):
                            pass
                    continue
            if _shell_probe_ready(last):
                return last
            await asyncio.sleep(0.5)
        raise TimeoutError(f"Chat shell not ready before deadline: {last}")

    async def _wait_shell_bridge_finish(
        self,
        last: dict[str, object],
        *,
        deadline: float,
        require_bridge: bool,
    ) -> dict[str, object]:
        if require_bridge:
            bridge_timeout = max(0.0, deadline - time.monotonic())
            if bridge_timeout > 0:
                await self.ensure_dev_bridge(
                    timeout_sec=min(bridge_timeout, 60.0),
                    allow_reload=True,
                )
            provider_timeout = max(0.0, deadline - time.monotonic())
            if provider_timeout > 0:
                await self._wait_providers_hydrated(
                    timeout_sec=min(provider_timeout, 45.0)
                )
            settle_deadline = time.monotonic() + 5.0
            stable = 0
            while time.monotonic() < settle_deadline and stable < 3:
                try:
                    probe = await self.evaluate(
                        PAGE_PROBE_JS,
                        intent=EvaluateIntent.SYNC_PROBE,
                    )
                except RuntimeError as exc:
                    message = str(exc)
                    if any(
                        token in message
                        for token in (
                            "Target closed",
                            "No page found",
                            "detached Frame",
                        )
                    ):
                        stable = 0
                        await asyncio.sleep(0.5)
                        continue
                    raise
                except TimeoutError:
                    stable = 0
                    await asyncio.sleep(0.5)
                    continue
                if (
                    isinstance(probe, dict)
                    and _shell_probe_ready(probe)
                    and probe.get("hasBridge")
                ):
                    stable += 1
                    last = probe
                else:
                    stable = 0
                await asyncio.sleep(0.3)
        return last

    async def _wait_shell_ready_inner(
        self,
        *,
        timeout_sec: float = 120.0,
        require_bridge: bool = True,
    ) -> dict[str, object]:
        deadline = time.monotonic() + timeout_sec
        last: dict[str, object] = {}
        polls = 0
        while time.monotonic() < deadline:
            polls += 1
            try:
                state = await self.evaluate(
                    PAGE_PROBE_JS,
                    intent=EvaluateIntent.SYNC_PROBE,
                )
            except RuntimeError as exc:
                message = str(exc)
                if any(
                    token in message
                    for token in ("Target closed", "No page found", "detached Frame")
                ):
                    await asyncio.sleep(1)
                    continue
                raise
            except TimeoutError:
                state = {"probeError": "evaluate_timeout"}
            last = state if isinstance(state, dict) else {"probeError": state}
            if _shell_probe_ready(last):
                if require_bridge:
                    bridge_timeout = max(0.0, deadline - time.monotonic())
                    if bridge_timeout > 0:
                        await self.ensure_dev_bridge(
                            timeout_sec=min(bridge_timeout, 60.0),
                            allow_reload=True,
                        )
                    provider_timeout = max(0.0, deadline - time.monotonic())
                    if provider_timeout > 0:
                        await self._wait_providers_hydrated(
                            timeout_sec=min(provider_timeout, 45.0)
                        )
                    settle_deadline = time.monotonic() + 5.0
                    stable = 0
                    while time.monotonic() < settle_deadline and stable < 3:
                        try:
                            probe = await self.evaluate(
                                PAGE_PROBE_JS,
                                intent=EvaluateIntent.SYNC_PROBE,
                            )
                        except RuntimeError as exc:
                            message = str(exc)
                            if any(
                                token in message
                                for token in (
                                    "Target closed",
                                    "No page found",
                                    "detached Frame",
                                )
                            ):
                                stable = 0
                                await asyncio.sleep(0.5)
                                continue
                            raise
                        except TimeoutError:
                            stable = 0
                            await asyncio.sleep(0.5)
                            continue
                        if (
                            isinstance(probe, dict)
                            and _shell_probe_ready(probe)
                            and probe.get("hasBridge")
                        ):
                            stable += 1
                        else:
                            stable = 0
                        await asyncio.sleep(0.3)
                return last
            if (
                isinstance(last, dict)
                and _blank_chat_shell_probe(last)
                and _bootstrap_shell_heal_polls(polls)
            ):
                heal = getattr(self, "_heal_empty_chat_shell_for_bridge", None)
                if callable(heal):
                    import sys

                    try:
                        from transport_supervisor import parallel_active_test_count

                        active = parallel_active_test_count()
                    except ImportError:
                        active = 1
                    heal_cap = _bootstrap_shell_heal_wall_cap_sec(active)
                    print(
                        "E2E_BOOTSTRAP_SHELL_HEAL: "
                        f"poll={polls} path={last.get('path')!r} "
                        f"parallel_active={active} wall_cap={heal_cap:.0f}s",
                        file=sys.stderr,
                        flush=True,
                    )
                    click_new = getattr(self, "click_new_chat", None)
                    if active >= 3 and callable(click_new):
                        try:
                            await asyncio.wait_for(
                                click_new(timeout_sec=min(60.0, heal_cap - 5.0)),
                                timeout=heal_cap,
                            )
                            continue
                        except TimeoutError as exc:
                            raise TimeoutError(
                                "E2E_BOOTSTRAP_SHELL_HEAL wall-timeout "
                                f"after {heal_cap:.0f}s parallel_active={active} "
                                "strategy=click_new_chat"
                            ) from exc
                    try:
                        await asyncio.wait_for(heal(), timeout=heal_cap)
                    except TimeoutError as exc:
                        raise TimeoutError(
                            "E2E_BOOTSTRAP_SHELL_HEAL wall-timeout "
                            f"after {heal_cap:.0f}s parallel_active={active} "
                            "strategy=navigate_heal"
                        ) from exc
                    continue
            await asyncio.sleep(0.5)
        extra = ""
        try:
            diag = await self.evaluate(
                "(() => ({ apiBase: window.__MYRM_E2E_API_BASE__, "
                "chatApi: window.__MYRM_E2E_CHAT__ ? {hasSetInput: !!window.__MYRM_E2E_CHAT__.setInputMessage, hasBridge: true} : null, "
                "layout: !!document.querySelector('[data-testid=\"app-layout\"]'), "
                "errDetails: (document.querySelector('details pre')?.innerText || '').slice(0, 1200), "
                "bodyText: (document.querySelector('body')?.innerText || '').slice(0, 120) }))()",
                intent=EvaluateIntent.SYNC_PROBE,
            )
            extra = f" diag={diag}"
        except (RuntimeError, TimeoutError):
            pass
        raise TimeoutError(f"Chat shell not ready within {timeout_sec:.0f}s: {last}{extra}")

    async def _wait_react_hydration(self, *, timeout_sec: float) -> None:
        """Wait until MessageInput hydrates. Skip reload — MCP-owned tabs detach on reload."""
        deadline = time.monotonic() + min(timeout_sec, 60.0)
        while time.monotonic() < deadline:
            try:
                hydrated = await self.evaluate(
                    """(() => {
                  const input = document.querySelector('[data-chat-input]');
                  const btn = document.querySelector('.message-send-btn');
                  const inputFiber = input
                    ? Object.keys(input).find((k) => k.startsWith('__reactFiber$'))
                    : null;
                  const btnFiber = btn
                    ? Object.keys(btn).find((k) => k.startsWith('__reactFiber$'))
                    : null;
                  const bridge = window.__MYRM_E2E_CHAT__;
                  return !!(inputFiber || btnFiber || bridge?.__e2eFallback === false);
                })()""",
                    intent=EvaluateIntent.SYNC_PROBE,
                )
            except RuntimeError as exc:
                if "Target closed" in str(exc) or "No page found" in str(exc):
                    return
                raise
            if hydrated is True:
                return
            await asyncio.sleep(2)

    async def _api_provider_ready_non_blocking(self, *, timeout_sec: float) -> bool:
        """Bound API readiness probe so provider checks cannot stall shell recovery."""
        probe_timeout = max(1.0, min(timeout_sec, 5.0))
        try:
            return bool(
                await asyncio.wait_for(
                    asyncio.to_thread(_api_provider_ready),
                    timeout=probe_timeout,
                )
            )
        except TimeoutError:
            import sys

            print(
                f"E2E_PROVIDER_READY_CHECK_TIMEOUT: timeout={probe_timeout:.1f}s",
                file=sys.stderr,
                flush=True,
            )
            return False
        except Exception:
            return False

    async def _wait_providers_hydrated(self, *, timeout_sec: float) -> None:
        """Wait until provider store is initialized; prefer E2E bridge over UI picker label."""
        if timeout_sec <= 0:
            return
        timeout_sec = max(5.0, min(timeout_sec, 60.0))
        if await self._api_provider_ready_non_blocking(timeout_sec=timeout_sec):
            deadline = time.monotonic() + timeout_sec
            try:
                await self.evaluate(
                    """(() => {
                      const bridge = window.__MYRM_E2E_CHAT__;
                      if (!bridge?.ensureProviders) return { ok: false };
                      return Promise.resolve(bridge.ensureProviders()).then(() => ({ ok: true }));
                    })()""",
                    intent=EvaluateIntent.AGENT_SUBMIT,
                )
            except (TimeoutError, RuntimeError):
                pass
            while time.monotonic() < deadline:
                try:
                    probe = await self.evaluate(
                        """(() => ({
                          init: !!window.__MYRM_E2E_CHAT__?.isProvidersInitialized?.(),
                          sendReady: !!window.__MYRM_E2E_CHAT__?.isSendReady?.(),
                        }))()""",
                        intent=EvaluateIntent.SYNC_PROBE,
                    )
                except RuntimeError:
                    await asyncio.sleep(0.5)
                    continue
                if isinstance(probe, dict) and probe.get("sendReady"):
                    return
                await asyncio.sleep(0.5)
            return

        deadline = time.monotonic() + timeout_sec
        while time.monotonic() < deadline:
            try:
                probe = await self.evaluate(
                    MODEL_PROBE_JS, intent=EvaluateIntent.SYNC_PROBE
                )
            except RuntimeError:
                await asyncio.sleep(0.5)
                continue
            if (
                isinstance(probe, dict)
                and probe.get("ok")
                and not probe.get("sendDisabled")
            ):
                return
            if isinstance(probe, dict) and not probe.get("unconfigured"):
                await asyncio.sleep(0.5)
                return
            await asyncio.sleep(1)

    async def dismiss_modals(self) -> None:
        await self.evaluate(DISMISS_MODALS_JS, intent=EvaluateIntent.SYNC_PROBE)
        await asyncio.sleep(0.5)

    async def navigate_to_chat(
        self,
        chat_id: str,
        base_url: str,
        *,
        timeout_sec: float = 60.0,
    ) -> None:
        expected_path = f"/{chat_id.strip()}"
        try:
            probe = await self.evaluate(
                "(() => ({ path: location.pathname }))()",
                intent=EvaluateIntent.SYNC_PROBE,
            )
        except RuntimeError:
            probe = None
        if isinstance(probe, dict) and str(probe.get("path") or "") == expected_path:
            await self.ensure_e2e_api_base_binding()
            await self.wait_shell_ready(timeout_sec=min(timeout_sec, 30.0))
            return
        import sys as _sys

        print(
            f"E2E_NAVIGATE_CHAT: before_path={probe.get('path') if isinstance(probe, dict) else 'probe_failed'} "
            f"expected={expected_path}",
            file=_sys.stderr,
            flush=True,
        )
        await self.ensure_e2e_api_base_binding()
        await self.cdp(
            "Page.navigate",
            {"url": base_url.rstrip("/") + expected_path},
            recv_timeout=120.0,
        )
        await asyncio.sleep(2)
        await self.ensure_e2e_api_base_binding()
        try:
            after_probe = await self.evaluate(
                "(() => ({ path: location.pathname, hasInput: !!document.querySelector('[data-chat-input]') }))()",
                intent=EvaluateIntent.SYNC_PROBE,
            )
        except RuntimeError:
            after_probe = {"probeError": "evaluate_timeout"}
        print(
            f"E2E_NAVIGATE_CHAT: after_path={after_probe.get('path') if isinstance(after_probe, dict) else after_probe}",
            file=_sys.stderr,
            flush=True,
        )
        await self.wait_shell_ready(timeout_sec=timeout_sec)

    async def _reload_chat_shell_burst(self) -> None:
        await self._shared_ui_burst(
            "reload",
            self.cdp("Page.reload", {"ignoreCache": True}, recv_timeout=120.0),
        )
        await asyncio.sleep(3.0)
        await self.ensure_e2e_api_base_binding()

    async def _hydrate_chat_home_surface(
        self,
        ui_base: str,
        *,
        deadline: float,
    ) -> None:
        remaining = max(0.0, deadline - time.monotonic())
        if remaining <= 0:
            raise TimeoutError("Chat surface hydrate budget exhausted")
        slice_sec = shpoib_shell_wait_slice_cap(remaining)
        self._check_shell_layout_stall_cap()
        self._shell_hydrate_depth += 1
        try:
            import sys

            print(
                "E2E_HYDRATE_HOME_START: navigate",
                file=sys.stderr,
                flush=True,
            )
            await self._shared_ui_burst(
                "navigate",
                self.cdp(
                    "Page.navigate",
                    {"url": f"{ui_base}/"},
                    recv_timeout=120.0,
                ),
            )
            print(
                "E2E_HYDRATE_HOME_PROGRESS: post_navigate binding",
                file=sys.stderr,
                flush=True,
            )
            await asyncio.sleep(2.0)
            await self.ensure_e2e_api_base_binding()
            # R53: inner poll only — avoid nested wait_shell_layout + mux deadlock.
            await self._wait_shell_ready_inner(
                timeout_sec=slice_sec,
                require_bridge=True,
            )
            await self._after_new_chat_reset(deadline=deadline)
            ensure_bridge = getattr(self, "ensure_react_e2e_bridge", None)
            if not callable(ensure_bridge):
                return
            bridge_remaining = max(0.0, deadline - time.monotonic())
            if bridge_remaining <= 0:
                return
            bridge_cap = min(90.0, shpoib_shell_wait_slice_cap(bridge_remaining))
            try:
                await ensure_bridge(timeout_sec=bridge_cap)
            except TimeoutError:
                await self._reload_chat_shell_burst()
        finally:
            self._shell_hydrate_depth -= 1

    async def ensure_chat_surface(
        self, base_url: str, *, timeout_sec: float = 90.0
    ) -> None:
        """Leave settings/onboarding routes before chat send automation."""
        ui_base = base_url.rstrip("/")
        timeout_sec = shpoib_parallel_shell_timeout_sec(timeout_sec)
        deadline = time.monotonic() + timeout_sec
        last: dict[str, object] = {"path": ""}
        self._mark_bootstrap_started()
        mux_recover_attempts = 0
        while time.monotonic() < deadline:
            try:
                from e2e_session_lifecycle import touch_wall_progress

                touch_wall_progress(current_node="ensure_chat_surface")
            except ImportError:
                pass
            self._check_bootstrap_stall_fail_fast(phase="ensure_chat_surface")
            try:
                probe = await self.evaluate(
                    PAGE_PROBE_JS,
                    intent=EvaluateIntent.SYNC_PROBE,
                )
            except RuntimeError as exc:
                from dev_gate_contract import MUX_RECLAIM_STALL_TOKEN

                if MUX_RECLAIM_STALL_TOKEN in str(exc):
                    if mux_recover_attempts < 1:
                        mux_recover_attempts = await self._recover_shell_probe_mux(
                            mux_recover_attempts
                        )
                        client = getattr(self, "_client", None)
                        abandon = getattr(client, "abandon_inflight_requests", None)
                        if callable(abandon):
                            abandon()
                        await asyncio.sleep(1.0)
                        continue
                    raise
                probe = {"probeError": "evaluate_failed"}
            except TimeoutError:
                probe = {"probeError": "evaluate_failed"}
            last = probe if isinstance(probe, dict) else {"probeError": probe}
            self._check_skeleton_stall(last, phase="ensure_chat_surface")
            path = str(last.get("path") or "")
            if path in ("blank", "", "about:blank") or not last.get("hasLayout"):
                await self._hydrate_chat_home_surface(ui_base, deadline=deadline)
                continue
            if path.startswith("/settings") or path == "/onboarding":
                await self._hydrate_chat_home_surface(ui_base, deadline=deadline)
                continue
            if path == "/" and not last.get("hasInput"):
                await self._hydrate_chat_home_surface(ui_base, deadline=deadline)
                continue
            if (
                (chat_id_from_path(path) is not None or last.get("hasInput"))
                and not path.startswith("/settings")
                and path != "/onboarding"
            ):
                return
            reset = await self.click_new_chat()
            if reset.get("ok"):
                await self._after_new_chat_reset(deadline=deadline)
                return
            await asyncio.sleep(0.5)
        raise RuntimeError(f"Chat surface not ready (path={last.get('path')}): {last}")

    async def _after_new_chat_reset(
        self,
        *,
        deadline: float | None = None,
        skip_shared_ui_contract: bool = False,
    ) -> None:
        """SHPOIB hot UI: re-bind private backend and refresh provider store after reset."""
        await self.ensure_e2e_api_base_binding()
        if not skip_shared_ui_contract:
            if self._shared_ui_session_contract_applied:
                await self._reapply_shared_ui_after_new_chat(deadline=deadline)
            else:
                await self._maybe_apply_shared_ui_session_contract(deadline=deadline)
        if self._shared_ui_session_contract_applied:
            bridge_cap = 90.0
            if deadline is not None:
                bridge_cap = max(
                    15.0,
                    min(90.0, deadline - time.monotonic()),
                )
            try:
                await self.evaluate(
                    """(() => {
                      const bridge = window.__MYRM_E2E_CHAT__;
                      if (!bridge?.ensureProviders) return { ok: false, err: 'no ensureProviders' };
                      bridge.prepareAutomationSend?.();
                      return Promise.resolve(bridge.ensureProviders()).then(() => ({ ok: true }));
                    })()""",
                    intent=EvaluateIntent.AGENT_SUBMIT,
                )
            except (RuntimeError, TimeoutError):
                pass
            await self.ensure_react_e2e_bridge(
                timeout_sec=bridge_cap,
                allow_reload=False,
            )
            return
        if deadline is not None and time.monotonic() >= deadline:
            raise TimeoutError("Chat surface provider reset budget exhausted")
        try:
            await self.evaluate(
                """(() => {
                  const bridge = window.__MYRM_E2E_CHAT__;
                  if (!bridge?.ensureProviders) return { ok: false, err: 'no ensureProviders' };
                  bridge.prepareAutomationSend?.();
                  return Promise.resolve(bridge.ensureProviders()).then(() => ({ ok: true }));
                })()""",
                intent=EvaluateIntent.AGENT_SUBMIT,
            )
        except (RuntimeError, TimeoutError):
            pass
        if deadline is not None and time.monotonic() >= deadline:
            return
        shell_cap = 45.0
        if deadline is not None:
            remaining = max(0.0, deadline - time.monotonic())
            if remaining <= 0:
                return
            shell_cap = max(5.0, shpoib_shell_wait_slice_cap(remaining))
        try:
            await self._wait_shell_ready_inner(
                timeout_sec=shell_cap,
                require_bridge=True,
            )
        except TimeoutError:
            bridge_cap = min(45.0, shell_cap)
            await self.ensure_dev_bridge(
                timeout_sec=bridge_cap,
                allow_reload=not self._shared_ui_session_contract_applied,
            )

    async def click_new_chat(
        self,
        *,
        timeout_sec: float | None = None,
        skip_shared_ui_contract: bool = False,
    ) -> dict[str, object]:
        reset_js = """
(() => {
  const bridge = window.__MYRM_E2E_CHAT__;
  if (bridge?.resetChat) {
    bridge.resetChat();
    return { ok: true, mode: 'bridge-reset' };
  }
  if (document.querySelector('[data-chat-input]')) {
    return { ok: true, mode: 'already' };
  }
  const newBtn = Array.from(document.querySelectorAll('aside button')).find((b) => {
    const text = (b.textContent || '').trim();
    return text.includes('新对话') || text.includes('New chat');
  });
  if (newBtn) {
    newBtn.click();
    return { ok: true, mode: 'new-chat' };
  }
  return { ok: false, mode: 'no-button' };
})()
""".strip()
        last: dict[str, object] = {"ok": False}
        deadline = (
            time.monotonic() + timeout_sec
            if timeout_sec is not None and timeout_sec > 0
            else None
        )
        for _ in range(8):
            if deadline is not None and time.monotonic() >= deadline:
                break
            try:
                result = await self.evaluate(
                    reset_js, intent=EvaluateIntent.SYNC_PROBE
                )
                last = (
                    result
                    if isinstance(result, dict)
                    else {"ok": False, "probeError": result}
                )
                if last.get("ok"):
                    await self._after_new_chat_reset(
                        deadline=deadline,
                        skip_shared_ui_contract=skip_shared_ui_contract,
                    )
                    await asyncio.sleep(0.5)
                    return last
            except TimeoutError as exc:
                if "Dev E2E chat bridge not available on WebUI" in str(exc):
                    await self._heal_empty_chat_shell_for_bridge()
                    await asyncio.sleep(1.0)
                    continue
                raise
            except RuntimeError as exc:
                message = str(exc)
                if any(
                    token in message
                    for token in ("detached Frame", "Target closed", "No page found")
                ):
                    await asyncio.sleep(1)
                    continue
                raise
            await asyncio.sleep(0.5)
        return last
