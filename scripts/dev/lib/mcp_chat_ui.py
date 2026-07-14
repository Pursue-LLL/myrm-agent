"""Chat UI session backed by the Chrome DevTools MCP mux owner model."""

from __future__ import annotations

import asyncio
import time

from cdp_chat_support import PAGE_PROBE_JS
from cdp_chat_ui import CdpChatSession
from chrome_mcp_client import ChromeMcpClient, McpPage

_DETACHED_FRAME_TOKENS = (
    "detached Frame",
    "Target closed",
    "No page found",
    "page has been closed",
    "selected page has been closed",
    "Execution context was destroyed",
)
_UPSTREAM_TIMEOUT_TOKENS = ("upstream request timed out",)
_EVALUATE_RETRY_ATTEMPTS = 5


def is_detached_frame_error(exc: BaseException) -> bool:
    message = str(exc)
    return any(token in message for token in _DETACHED_FRAME_TOKENS)


def is_upstream_timeout_error(exc: BaseException) -> bool:
    message = str(exc)
    return any(token in message for token in _UPSTREAM_TIMEOUT_TOKENS)


def is_recoverable_evaluate_error(exc: BaseException) -> bool:
    return is_detached_frame_error(exc) or is_upstream_timeout_error(exc)


class McpChatSession(CdpChatSession):
    def __init__(self, client: ChromeMcpClient, page: McpPage) -> None:
        self._client = client
        self._page = page
        self._base_url = "http://127.0.0.1:3000"

    async def evaluate(
        self,
        expression: str,
        *,
        await_promise: bool = True,
        recv_timeout: float = 60.0,
    ) -> object:
        del await_promise
        last_exc: RuntimeError | None = None
        for attempt in range(_EVALUATE_RETRY_ATTEMPTS):
            try:
                return await asyncio.to_thread(
                    self._client.evaluate,
                    self._page,
                    expression,
                    timeout_sec=min(recv_timeout, 45.0),
                )
            except RuntimeError as exc:
                if not is_recoverable_evaluate_error(exc):
                    raise
                last_exc = exc
                if attempt >= 2:
                    await self.recreate_page()
                elif attempt >= 1:
                    await self._recover_page()
                await asyncio.sleep(0.5 * (attempt + 1))
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("MCP evaluate failed without exception")

    async def _recover_page(self) -> None:
        try:
            await asyncio.to_thread(
                self._client.navigate,
                self._page,
                self._base_url,
                timeout_ms=30_000,
            )
        except RuntimeError:
            return
        await asyncio.sleep(1.0)

    async def recreate_page(self, *, timeout_ms: int = 120_000) -> None:
        old_page = self._page
        try:
            await asyncio.to_thread(self._client.close_page, old_page, ignore_errors=True)
        except RuntimeError:
            pass
        self._page = await asyncio.to_thread(
            self._client.new_page,
            self._base_url,
            timeout_ms=timeout_ms,
        )
        deadline = time.monotonic() + 90.0
        while time.monotonic() < deadline:
            try:
                probe = await asyncio.to_thread(
                    self._client.evaluate,
                    self._page,
                    PAGE_PROBE_JS,
                    timeout_sec=10.0,
                )
            except RuntimeError:
                await asyncio.sleep(0.5)
                continue
            if isinstance(probe, dict) and probe.get("hasInput"):
                await self.ensure_dev_bridge(timeout_sec=30.0, allow_reload=False)
                return
            await asyncio.sleep(0.5)
        raise TimeoutError("MCP page recreation failed to hydrate chat shell")

    async def bootstrap(
        self,
        base_url: str,
        *,
        timeout_sec: float = 180.0,
        navigate: bool = False,
    ) -> dict[str, object]:
        del navigate
        self._base_url = base_url
        await asyncio.sleep(1.0)
        return await self.wait_shell_ready(timeout_sec=timeout_sec, require_bridge=True)

    async def ensure_dev_bridge(
        self, *, timeout_sec: float = 90.0, allow_reload: bool = True
    ) -> None:
        del allow_reload
        await super().ensure_dev_bridge(timeout_sec=timeout_sec, allow_reload=False)

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
        if method == "Page.reload":
            return {}
        if method == "Page.navigate":
            url = arguments.get("url")
            if not isinstance(url, str):
                raise RuntimeError("Page.navigate requires url")
            await asyncio.to_thread(
                self._client.navigate,
                self._page,
                url,
                timeout_ms=min(int(recv_timeout * 1000), 15_000),
            )
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
