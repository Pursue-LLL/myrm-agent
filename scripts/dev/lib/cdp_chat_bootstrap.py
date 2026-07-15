"""Chat shell bootstrap and hydration workflow."""

from __future__ import annotations

import asyncio
import time

from cdp_chat_support import (
    DISMISS_MODALS_JS,
    MODEL_PROBE_JS,
    PAGE_PROBE_JS,
    RESET_CHAT_JS,
    _api_provider_ready,
    e2e_api_base_inject_js,
    e2e_api_base_persist_source,
)
from cdp_chat_transport import CdpChatTransport


def _shell_probe_ready(probe: dict[str, object]) -> bool:
    if probe.get("skeleton"):
        return False
    if probe.get("hasInput"):
        return True
    return bool(
        probe.get("hasBridge")
        and probe.get("clientHydrated")
        and probe.get("hasLayout")
    )


class CdpChatBootstrap(CdpChatTransport):
    _e2e_api_base_bound: bool = False

    async def ensure_e2e_api_base_binding(self) -> None:
        """Register persistent new-document hook once + immediate inject for SHPOIB private pools."""
        source = e2e_api_base_persist_source()
        if not source:
            return
        if not self._e2e_api_base_bound:
            await self.cdp("Page.addScriptToEvaluateOnNewDocument", {"source": source})
            self._e2e_api_base_bound = True
        await self.evaluate(e2e_api_base_inject_js(), await_promise=False)

    async def bootstrap(
        self,
        base_url: str,
        *,
        timeout_sec: float = 180.0,
        navigate: bool = False,
    ) -> dict[str, object]:
        deadline = time.monotonic() + timeout_sec
        last: dict[str, object] = {}
        await self.cdp("Runtime.enable")
        await self.cdp("Page.enable")
        await self.ensure_e2e_api_base_binding()
        if navigate:
            probe = await self.evaluate(PAGE_PROBE_JS, await_promise=False)
            if not (isinstance(probe, dict) and probe.get("hasInput") and not probe.get("skeleton")):
                await self.cdp(
                    "Page.navigate",
                    {"url": base_url.rstrip("/") + "/"},
                    recv_timeout=120.0,
                )
                await asyncio.sleep(2)
        else:
            await asyncio.sleep(2)
        polls = 0
        shell_ready = False
        while time.monotonic() < deadline:
            polls += 1
            try:
                state = await self.evaluate(PAGE_PROBE_JS, await_promise=False)
            except TimeoutError:
                state = {"probeError": "evaluate_timeout"}
            last = state if isinstance(state, dict) else {"probeError": state}
            if _shell_probe_ready(last):
                shell_ready = True
                break
            if (
                not navigate
                and polls == 20
                and not last.get("hasInput")
            ):
                await self.cdp(
                    "Page.navigate",
                    {"url": base_url.rstrip("/") + "/"},
                    recv_timeout=120.0,
                )
                await asyncio.sleep(3)
            if isinstance(last, dict) and last.get("hasLayout") is False and polls % 15 == 0:
                await self.cdp("Page.reload", {"ignoreCache": True}, recv_timeout=120.0)
                await asyncio.sleep(3)
            if polls % 10 == 0:
                await self.evaluate(RESET_CHAT_JS, await_promise=False)
            await asyncio.sleep(1)
        if not shell_ready:
            raise TimeoutError(f"Chat shell not ready within {timeout_sec:.0f}s: {last}")

        bridge_timeout = max(0.0, deadline - time.monotonic())
        if bridge_timeout > 0:
            await self.ensure_dev_bridge(timeout_sec=min(bridge_timeout, 90.0))
            hydrate_timeout = max(0.0, deadline - time.monotonic())
            if hydrate_timeout > 0:
                await self._wait_react_hydration(timeout_sec=hydrate_timeout)
            provider_timeout = max(0.0, deadline - time.monotonic())
            if provider_timeout > 0:
                await self._wait_providers_hydrated(timeout_sec=min(provider_timeout, 60.0))
            last = await self.evaluate(PAGE_PROBE_JS, await_promise=False)
            if not isinstance(last, dict):
                last = {"probeError": last}
        return last

    async def wait_shell_ready(
        self,
        *,
        timeout_sec: float = 120.0,
        require_bridge: bool = True,
    ) -> dict[str, object]:
        """Lightweight shell wait for MCP pages already navigated to the app URL."""
        deadline = time.monotonic() + timeout_sec
        last: dict[str, object] = {}
        while time.monotonic() < deadline:
            try:
                state = await self.evaluate(PAGE_PROBE_JS, await_promise=False)
            except RuntimeError as exc:
                message = str(exc)
                if any(token in message for token in ("Target closed", "No page found", "detached Frame")):
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
                        await self._wait_providers_hydrated(timeout_sec=min(provider_timeout, 45.0))
                    settle_deadline = time.monotonic() + 5.0
                    stable = 0
                    while time.monotonic() < settle_deadline and stable < 3:
                        try:
                            probe = await self.evaluate(
                                PAGE_PROBE_JS,
                                await_promise=False,
                                recv_timeout=min(15.0, max(5.0, settle_deadline - time.monotonic())),
                            )
                        except RuntimeError as exc:
                            message = str(exc)
                            if any(token in message for token in ("Target closed", "No page found", "detached Frame")):
                                stable = 0
                                await asyncio.sleep(0.5)
                                continue
                            raise
                        except TimeoutError:
                            stable = 0
                            await asyncio.sleep(0.5)
                            continue
                        if isinstance(probe, dict) and _shell_probe_ready(probe) and probe.get("hasBridge"):
                            stable += 1
                        else:
                            stable = 0
                        await asyncio.sleep(0.3)
                return last
            await asyncio.sleep(0.5)
        raise TimeoutError(f"Chat shell not ready within {timeout_sec:.0f}s: {last}")

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
                    await_promise=False,
                )
            except RuntimeError as exc:
                if "Target closed" in str(exc) or "No page found" in str(exc):
                    return
                raise
            if hydrated is True:
                return
            await asyncio.sleep(2)

    async def _wait_providers_hydrated(self, *, timeout_sec: float) -> None:
        """Wait until provider store is initialized; prefer E2E bridge over UI picker label."""
        if _api_provider_ready():
            deadline = time.monotonic() + timeout_sec
            try:
                await self.evaluate(
                    """(() => {
                      const bridge = window.__MYRM_E2E_CHAT__;
                      if (!bridge?.ensureProviders) return { ok: false };
                      return Promise.resolve(bridge.ensureProviders()).then(() => ({ ok: true }));
                    })()""",
                    await_promise=True,
                    recv_timeout=min(timeout_sec, 60.0),
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
                        await_promise=False,
                    )
                except RuntimeError:
                    await asyncio.sleep(0.5)
                    continue
                if isinstance(probe, dict) and (probe.get("sendReady") or probe.get("init")):
                    return
                await asyncio.sleep(0.5)
            return

        deadline = time.monotonic() + timeout_sec
        while time.monotonic() < deadline:
            try:
                probe = await self.evaluate(MODEL_PROBE_JS, await_promise=False)
            except RuntimeError:
                await asyncio.sleep(0.5)
                continue
            if isinstance(probe, dict) and probe.get("ok") and not probe.get("sendDisabled"):
                return
            if isinstance(probe, dict) and not probe.get("unconfigured"):
                await asyncio.sleep(0.5)
                return
            await asyncio.sleep(1)

    async def dismiss_modals(self) -> None:
        await self.evaluate(DISMISS_MODALS_JS, await_promise=False)
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
                await_promise=False,
            )
        except RuntimeError:
            probe = None
        if isinstance(probe, dict) and str(probe.get("path") or "") == expected_path:
            await self.ensure_e2e_api_base_binding()
            await self.wait_shell_ready(timeout_sec=min(timeout_sec, 30.0))
            return
        await self.ensure_e2e_api_base_binding()
        await self.cdp(
            "Page.navigate",
            {"url": base_url.rstrip("/") + expected_path},
            recv_timeout=120.0,
        )
        await asyncio.sleep(2)
        await self.ensure_e2e_api_base_binding()
        await self.wait_shell_ready(timeout_sec=timeout_sec)

    async def _after_new_chat_reset(self) -> None:
        """SHPOIB hot UI: re-bind private backend and refresh provider store after reset."""
        await self.ensure_e2e_api_base_binding()
        try:
            await self.evaluate(
                """(() => {
                  const bridge = window.__MYRM_E2E_CHAT__;
                  if (!bridge?.ensureProviders) return { ok: false, err: 'no ensureProviders' };
                  bridge.prepareAutomationSend?.();
                  return Promise.resolve(bridge.ensureProviders()).then(() => ({ ok: true }));
                })()""",
                await_promise=True,
                recv_timeout=45.0,
            )
        except (RuntimeError, TimeoutError):
            pass
        try:
            await self.wait_shell_ready(timeout_sec=45.0, require_bridge=True)
        except TimeoutError:
            await self.ensure_dev_bridge(timeout_sec=45.0, allow_reload=True)

    async def click_new_chat(self) -> dict[str, object]:
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
        for _ in range(8):
            try:
                result = await self.evaluate(reset_js, await_promise=False)
                last = result if isinstance(result, dict) else {"ok": False, "probeError": result}
                if last.get("ok"):
                    await self._after_new_chat_reset()
                    await asyncio.sleep(0.5)
                    return last
            except RuntimeError as exc:
                message = str(exc)
                if any(token in message for token in ("detached Frame", "Target closed", "No page found")):
                    await asyncio.sleep(1)
                    continue
                raise
            await asyncio.sleep(0.5)
        return last

