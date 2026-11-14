"""The bootstrap flow: deadlines, warm-shell probe, shell-ready and bridge-hydrate phases."""

from __future__ import annotations

import asyncio
import os
import time

from dev_gate.contract import EvaluateIntent

from cdp_chat.bootstrap.binding import _signoff_bridge_hydrate_cap_sec
from cdp_chat.bootstrap.shell_ready import _bootstrap_monorepo_root
from cdp_chat.bootstrap.surface import _BootstrapSurface, _parallel_shpoib_shell_timeout
from cdp_chat.support import PAGE_PROBE_JS
from cdp_chat.transport import CdpChatTransport


def split_bootstrap_deadlines(
    timeout_sec: float,
    *,
    now: float | None = None,
) -> tuple[float, float]:
    """Return ``(shell_deadline, bridge_deadline)`` with bridge hydrate reserve.

    Parallel SHPOIB scales the outer bootstrap wall for shell mux contention but
    must not consume the shared UI session contract budget (RESET_GLOBALS…).
    """
    from dev_gate.contract import (
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


class CdpChatBootstrap(_BootstrapSurface):
    """Chat shell bootstrap and hydration workflow (the top layer of the chain, see `cdp_chat.bootstrap`)."""

    async def bootstrap(
        self,
        base_url: str,
        *,
        timeout_sec: float = 180.0,
        navigate: bool = False,
    ) -> dict[str, object]:
        from e2e_session_runtime.lifecycle import (  # noqa: PLC0415
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
                from e2e_core.warm_ui_heal import ensure_shared_ui_before_cdp_navigate

                probe_dict = probe if isinstance(probe, dict) else None
                await asyncio.to_thread(
                    ensure_shared_ui_before_cdp_navigate,
                    _bootstrap_monorepo_root(),
                    probe=probe_dict,
                )
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
            from e2e_session_runtime.lifecycle import current_phase, remaining_wall_sec

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
        from e2e_session_runtime.lifecycle import complete_bootstrap_phase

        complete_bootstrap_phase(phase_label="post_cdp_bootstrap")
        return last

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
