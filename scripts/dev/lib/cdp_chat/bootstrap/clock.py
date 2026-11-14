"""Bootstrap clocks and stall guards: when a bootstrap, shell session or layout wait started and when it has stalled."""

from __future__ import annotations

import os
import time
from typing import TYPE_CHECKING

from cdp_chat.transport import CdpChatTransport

_SHELL_PROBE_PROGRESS_INTERVAL_SEC = 30.0


def _shell_probe_stall_cap_sec() -> float:
    from dev_gate.contract import SHELL_PROBE_STALL_FAIL_FAST_SEC

    cap = float(SHELL_PROBE_STALL_FAIL_FAST_SEC)
    # Shared-hot desktop chrome_e2e can require longer mux reclaim/hydration.
    if os.environ.get("MYRM_E2E_SHARED_HOT", "").strip() == "1":
        cap = max(cap, 180.0)
    if os.environ.get("E2E_SIGNOFF", "").strip() == "1":
        cap = max(cap, 180.0)
        try:
            from chrome_mcp.client import _parallel_mux_peer_count

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


class _BootstrapClock(CdpChatTransport):
    _e2e_api_base_bound: bool = False
    _shared_ui_session_contract_applied: bool = False
    _bootstrap_started_monotonic: float | None = None
    # Session SSOT: hydrate re-entry must not reset shell-layout stall clock.
    _shell_layout_wait_started: float | None = None
    # session-level stall clock — never reset on mux recover retry.
    _shell_session_started: float | None = None
    _shell_skeleton_since: float | None = None
    _shell_hydrate_depth: int = 0

    if TYPE_CHECKING:
        # Bridge hooks implemented by the CdpChatInput subclass; declared here so every layer
        # type-checks against the real signatures. They add nothing at runtime.
        async def ensure_dev_bridge(self, *, timeout_sec: float = 90.0, allow_reload: bool = True) -> None: ...

        async def ensure_react_e2e_bridge(
            self, *, timeout_sec: float = 90.0, allow_reload: bool | None = None
        ) -> None: ...

        async def _heal_empty_chat_shell_for_bridge(self) -> None: ...

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
        """Fail-fast when UI stays skeleton/blank without progress."""
        from dev_gate.contract import (
            E2E_SHELL_SKELETON_STALL_TOKEN,
            shell_probe_stall_fail_fast_effective_sec,
        )

        # Chat shell is interactive — Loading messages skeleton may linger in DOM during stream.
        if (
            probe.get("hasInput")
            and probe.get("hasBridge")
            and probe.get("hasLayout")
            and probe.get("clientHydrated")
        ):
            self._shell_skeleton_since = None
            return

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
        from dev_gate.contract import (
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
            from e2e_core.orchestrator import assert_wall_budget

            assert_wall_budget(phase)
            return
        except ImportError:
            pass
        from dev_gate.contract import (
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
            from e2e_session_runtime.lifecycle import touch_wall_progress

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
