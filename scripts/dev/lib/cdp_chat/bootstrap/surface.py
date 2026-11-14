"""Page-level entry points: wait for the shell, navigate to chat, leave non-chat routes and open a new chat."""

from __future__ import annotations

import asyncio
import os
import time

from dev_gate.contract import EvaluateIntent

from cdp_chat.bootstrap.layout import _BootstrapLayout
from cdp_chat.support import PAGE_PROBE_JS, chat_id_from_path, shpoib_parallel_shell_timeout_sec


def _parallel_shpoib_shell_timeout(timeout_sec: float) -> float:
    return shpoib_parallel_shell_timeout_sec(timeout_sec)


class _BootstrapSurface(_BootstrapLayout):
    async def wait_shell_ready(
        self,
        *,
        timeout_sec: float = 120.0,
        require_bridge: bool = True,
    ) -> dict[str, object]:
        """Lightweight shell wait for MCP pages already navigated to the app URL."""
        from dev_gate.contract import MUX_RECLAIM_STALL_TOKEN

        timeout_sec = _parallel_shpoib_shell_timeout(timeout_sec)
        self._reset_shell_layout_wait_clock()
        self._mark_bootstrap_started()
        # parallel SHPOIB uses inner poll — nested wait_shell_layout mux-deadlocks.
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
                from e2e_session_runtime.lifecycle import touch_wall_progress

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
                from dev_gate.contract import MUX_RECLAIM_STALL_TOKEN

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
