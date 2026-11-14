"""Layout-level waits: hydrate the chat home surface and wait for the shell layout with stall detection."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable

from dev_gate.contract import EvaluateIntent

from cdp_chat.bootstrap.clock import _shell_probe_ready, _shell_probe_stall_cap_sec
from cdp_chat.bootstrap.shell_ready import _BootstrapShellReady
from cdp_chat.support import PAGE_PROBE_JS, get_e2e_ui_url, shpoib_shell_wait_slice_cap

_SHELL_PROBE_RECV_TIMEOUT_SEC = 15.0
_SHELL_PROBE_POLL_HARD_TIMEOUT_SEC = 75.0


class _BootstrapLayout(_BootstrapShellReady):
    async def _wait_shell_layout_ready(self, *, deadline: float) -> dict[str, object]:
        from dev_gate.contract import (
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
            # inner poll only — avoid nested wait_shell_layout + mux deadlock.
            await self._wait_shell_ready_inner(
                timeout_sec=slice_sec,
                require_bridge=True,
            )
            await self._after_new_chat_reset(deadline=deadline)
            ensure_bridge: Callable[..., Awaitable[None]] | None = getattr(
                self, "ensure_react_e2e_bridge", None
            )
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
