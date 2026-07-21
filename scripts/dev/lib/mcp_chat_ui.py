"""Chat UI session backed by the Chrome DevTools MCP mux owner model."""

from __future__ import annotations

import asyncio
import os
import time

from cdp_chat_support import PAGE_PROBE_JS, e2e_api_base_inject_js
from cdp_chat_ui import CdpChatSession
from chrome_mcp_client import (
    ChromeMcpClient,
    McpPage,
    is_context_reset_error,
    is_page_ownership_error,
)

_DETACHED_FRAME_TOKENS = (
    "detached Frame",
    "Execution context was destroyed",
)


def is_detached_frame_error(exc: BaseException) -> bool:
    message = str(exc)
    return any(token in message for token in _DETACHED_FRAME_TOKENS)


def is_mux_page_heal_error(exc: BaseException) -> bool:
    return is_page_ownership_error(exc) or is_context_reset_error(exc)


def _default_e2e_ui_base() -> str:
    return os.getenv("E2E_UI_BASE", "http://127.0.0.1:3000").rstrip("/")


def _path_needs_chat_navigate(path: str) -> bool:
    normalized = path.strip().strip("/")
    return normalized in {"", "blank", "about:blank"}


class McpChatSession(CdpChatSession):
    def __init__(self, client: ChromeMcpClient, page: McpPage) -> None:
        self._client = client
        self._page = page
        self._base_url = _default_e2e_ui_base()

    async def evaluate(
        self,
        expression: str,
        *,
        await_promise: bool = True,
        recv_timeout: float = 60.0,
    ) -> object:
        del await_promise
        if recv_timeout <= 0:
            raise ValueError("recv_timeout must be positive")
        heal_attempts = 0
        max_heal_attempts = 3
        mux_attempts = 0
        max_mux_attempts = 3
        while True:
            try:
                return await asyncio.to_thread(
                    self._client.evaluate,
                    self._page,
                    expression,
                    timeout_sec=recv_timeout,
                )
            except TimeoutError:
                mux_attempts += 1
                if mux_attempts < max_mux_attempts:
                    await asyncio.sleep(0.75 * mux_attempts)
                    continue
                raise
            except RuntimeError as exc:
                if heal_attempts < max_heal_attempts and is_detached_frame_error(exc):
                    heal_attempts += 1
                    await self._heal_detached_page()
                    continue
                if heal_attempts < max_heal_attempts and is_mux_page_heal_error(exc):
                    heal_attempts += 1
                    await self._heal_reclaimed_page()
                    continue
                raise

    async def _inject_e2e_api_base(self) -> None:
        inject_js = e2e_api_base_inject_js()
        if not inject_js:
            return
        try:
            await self.evaluate(inject_js, await_promise=False, recv_timeout=15.0)
        except RuntimeError:
            pass

    async def _heal_reclaimed_page(self) -> None:
        reopened = await asyncio.to_thread(
            self._client.reclaim_owned_page,
            self._page,
        )
        self._page = reopened
        await asyncio.sleep(1.0)
        await self._inject_e2e_api_base()
        try:
            await self.wait_shell_ready(timeout_sec=60.0, require_bridge=True)
        except TimeoutError:
            pass

    async def _heal_detached_page(self) -> None:
        await asyncio.to_thread(
            self._client.navigate,
            self._page,
            f"{self._base_url.rstrip('/')}/",
            timeout_ms=60_000,
        )
        await asyncio.sleep(2.0)
        await self._inject_e2e_api_base()
        try:
            await self.wait_shell_ready(timeout_sec=60.0, require_bridge=True)
        except TimeoutError:
            pass

    async def _navigate_to_chat_home(self, *, timeout_ms: int = 120_000) -> None:
        ui_base = self._base_url.rstrip("/")
        await asyncio.to_thread(
            self._client.navigate,
            self._page,
            f"{ui_base}/",
            timeout_ms=timeout_ms,
        )
        await asyncio.sleep(2.0)
        await self._inject_e2e_api_base()

    async def bootstrap(
        self,
        base_url: str,
        *,
        timeout_sec: float = 120.0,
        navigate: bool = False,
    ) -> dict[str, object]:
        self._base_url = base_url
        await asyncio.sleep(1.0)
        await self.ensure_e2e_api_base_binding()
        should_navigate = navigate
        if not should_navigate:
            try:
                probe = await self.evaluate(
                    PAGE_PROBE_JS,
                    await_promise=False,
                    recv_timeout=15.0,
                )
            except (RuntimeError, TimeoutError):
                probe = None
            if not isinstance(probe, dict) or not probe.get("hasLayout"):
                should_navigate = True
            else:
                path = str(probe.get("path") or "")
                should_navigate = _path_needs_chat_navigate(path)
        if should_navigate:
            await self._navigate_to_chat_home(
                timeout_ms=min(int(timeout_sec * 1000), 120_000),
            )
        return await self.wait_shell_ready(timeout_sec=timeout_sec, require_bridge=True)

    async def wait_shell_ready(
        self,
        *,
        timeout_sec: float = 120.0,
        require_bridge: bool = True,
    ) -> dict[str, object]:
        deadline = time.monotonic() + timeout_sec
        last_exc: TimeoutError | None = None
        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            try:
                probe = await self.evaluate(
                    PAGE_PROBE_JS,
                    await_promise=False,
                    recv_timeout=15.0,
                )
            except (RuntimeError, TimeoutError):
                probe = None
            if isinstance(probe, dict):
                path = str(probe.get("path") or "")
                if _path_needs_chat_navigate(path) or not probe.get("hasLayout"):
                    await self._navigate_to_chat_home(
                        timeout_ms=max(15_000, int(remaining * 1000)),
                    )
            try:
                return await super().wait_shell_ready(
                    timeout_sec=min(remaining, 60.0),
                    require_bridge=require_bridge,
                )
            except TimeoutError as exc:
                last_exc = exc
                await asyncio.sleep(0.5)
        raise last_exc or TimeoutError(
            f"Chat shell not ready within {timeout_sec:.0f}s"
        )

    async def ensure_dev_bridge(
        self, *, timeout_sec: float = 90.0, allow_reload: bool = True
    ) -> None:
        await super().ensure_dev_bridge(
            timeout_sec=timeout_sec,
            allow_reload=allow_reload,
        )

    async def cdp(
        self,
        method: str,
        params: dict[str, object] | None = None,
        *,
        recv_timeout: float = 30.0,
    ) -> dict[str, object]:
        arguments = params or {}
        if method in {"Runtime.enable", "Page.enable", "DOM.enable"}:
            return {}
        if method == "Page.addScriptToEvaluateOnNewDocument":
            # MCP mux has no raw CDP; ensure_e2e_api_base_binding injects on the live document.
            return {}
        if method == "Page.reload":
            await asyncio.to_thread(
                self._client.reload,
                self._page,
                timeout_ms=min(int(recv_timeout * 1000), 120_000),
            )
            await asyncio.sleep(4.0)
            await self._inject_e2e_api_base()
            return {}
        if method == "Page.navigate":
            url = arguments.get("url")
            if not isinstance(url, str):
                raise RuntimeError("Page.navigate requires url")
            await asyncio.to_thread(
                self._client.navigate,
                self._page,
                url,
                timeout_ms=min(int(recv_timeout * 1000), 60_000),
            )
            await self._inject_e2e_api_base()
            return {}
        if method == "Input.insertText":
            text = arguments.get("text")
            if isinstance(text, str):
                await asyncio.to_thread(self._client.type_text, self._page, text)
            return {}
        if method == "Input.dispatchKeyEvent":
            if arguments.get("type") != "keyDown":
                return {}
            key = str(arguments.get("key") or "")
            modifiers = int(arguments.get("modifiers") or 0)
            if modifiers & 4:
                key = f"Meta+{key}"
            elif modifiers & 2:
                key = f"Control+{key}"
            if key:
                await asyncio.to_thread(self._client.press_key, self._page, key)
            return {}
        if method in {"DOM.getDocument", "DOM.querySelector", "DOM.getBoxModel"}:
            return {}
        raise RuntimeError(f"Unsupported CDP fallback through MCP: {method}")
