"""Chat UI session backed by the Chrome DevTools MCP mux owner model."""

from __future__ import annotations

import asyncio
import os

from cdp_chat_support import e2e_api_base_inject_js
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
        while True:
            try:
                return await asyncio.to_thread(
                    self._client.evaluate,
                    self._page,
                    expression,
                    timeout_sec=min(recv_timeout, 120.0),
                )
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
            self._base_url,
            timeout_ms=60_000,
        )
        await asyncio.sleep(2.0)
        await self._inject_e2e_api_base()
        try:
            await self.wait_shell_ready(timeout_sec=60.0, require_bridge=True)
        except TimeoutError:
            pass

    async def bootstrap(
        self,
        base_url: str,
        *,
        timeout_sec: float = 120.0,
        navigate: bool = False,
    ) -> dict[str, object]:
        del navigate
        self._base_url = base_url
        await asyncio.sleep(1.0)
        return await self.wait_shell_ready(timeout_sec=timeout_sec, require_bridge=True)

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
