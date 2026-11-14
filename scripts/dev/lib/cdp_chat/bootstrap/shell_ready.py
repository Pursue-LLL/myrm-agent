"""Waits for a navigated page to become a ready chat shell, healing blank or stalled shells, and the new-chat reset."""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path

from dev_gate.contract import EvaluateIntent

from cdp_chat.bootstrap.binding import _BootstrapBinding
from cdp_chat.bootstrap.clock import _shell_probe_ready
from cdp_chat.support import PAGE_PROBE_JS, shpoib_shell_wait_slice_cap


def _bootstrap_monorepo_root() -> Path:
    raw = os.environ.get("MYRM_MONOREPO_ROOT", "").strip()
    if raw:
        return Path(raw)
    return Path(__file__).resolve().parents[6]


def _blank_chat_shell_probe(probe: dict[str, object]) -> bool:
    """True when shared UI tab lost chat shell under parallel UI hydrate."""
    if probe.get("skeleton"):
        return False
    if probe.get("hasInput") or probe.get("hasBridge"):
        return False
    path = str(probe.get("path") or "/").strip() or "/"
    return path == "/"


def _bootstrap_shell_heal_polls(poll: int) -> bool:
    return poll in {1, 8, 20, 35, 50, 65}


def _bootstrap_shell_heal_wall_cap_sec(parallel_active: int) -> float:
    """fail-fast shell heal under parallel mux so soak mux_retry can recover."""
    load = max(0, int(parallel_active))
    if load >= 4:
        return 75.0
    if load >= 2:
        return 90.0
    return 120.0


class _BootstrapShellReady(_BootstrapBinding):
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
                        from mux.transport_supervisor import parallel_active_test_count

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
                        from e2e_core.warm_ui_heal import (
                            ensure_shared_ui_before_cdp_navigate,
                            probe_indicates_ui_connection_refused,
                        )

                        if isinstance(last, dict) and probe_indicates_ui_connection_refused(
                            last
                        ):
                            await asyncio.to_thread(
                                ensure_shared_ui_before_cdp_navigate,
                                _bootstrap_monorepo_root(),
                                probe=last,
                            )
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
