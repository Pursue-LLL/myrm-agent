"""API base binding, provider and React hydration waits, modal dismissal, mux recovery and the shared UI session contract."""

from __future__ import annotations

import asyncio
import os
import time

from dev_gate.contract import EvaluateIntent

from cdp_chat.bootstrap.clock import _BootstrapClock
from cdp_chat.support import (
    DISMISS_MODALS_JS,
    MODEL_PROBE_JS,
    _api_provider_ready,
    e2e_api_base_inject_js,
    e2e_api_base_persist_source,
    e2e_runtime_bootstrap_apply_js,
)


def _signoff_bridge_hydrate_cap_sec() -> float:
    """scale bridge/shared-ui hydrate slice under parallel signoff (v149 @9 leases)."""
    cap = 90.0
    if os.environ.get("E2E_SIGNOFF", "").strip() != "1":
        return cap
    try:
        from dev_gate.contract.parallel_pressure import parallel_signoff_pressure_peers

        peers = parallel_signoff_pressure_peers()
        if peers >= 2:
            return min(180.0, 90.0 + peers * 10.0)
    except ImportError:
        pass
    return cap


class _BootstrapBinding(_BootstrapClock):
    async def _shared_ui_burst(self, operation: str, action):
        from e2e_core.shared_ui_hydrate import async_shared_ui_hydrate_burst

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

    async def _maybe_apply_shared_ui_session_contract(
        self,
        *,
        deadline: float | None = None,
    ) -> None:
        from e2e_core.shared_ui_session import maybe_apply_shared_ui_session_contract

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
        from e2e_core.shared_ui_session import reapply_shared_ui_session_after_new_chat

        await reapply_shared_ui_session_after_new_chat(self, deadline=deadline)

    async def _recover_shell_probe_mux(self, mux_recover_attempts: int) -> int:
        from dev_gate.contract import MUX_RECLAIM_STALL_TOKEN

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

    async def _reload_chat_shell_burst(self) -> None:
        await self._shared_ui_burst(
            "reload",
            self.cdp("Page.reload", {"ignoreCache": True}, recv_timeout=120.0),
        )
        await asyncio.sleep(3.0)
        await self.ensure_e2e_api_base_binding()
