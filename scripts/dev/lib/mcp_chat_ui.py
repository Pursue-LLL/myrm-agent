"""Chat UI session backed by the Chrome DevTools MCP mux owner model."""

from __future__ import annotations

import asyncio

from cdp_chat_ui import CdpChatSession
from chrome_mcp_client import ChromeMcpClient, McpPage

_DETACHED_FRAME_TOKENS = (
    "detached Frame",
    "Execution context was destroyed",
)

_RECOVERABLE_EVAL_TOKENS = (
    *_DETACHED_FRAME_TOKENS,
    "No page found",
    "Target closed",
)


def is_detached_frame_error(exc: BaseException) -> bool:
    message = str(exc)
    return any(token in message for token in _DETACHED_FRAME_TOKENS)


def is_recoverable_evaluate_error(exc: BaseException) -> bool:
    message = str(exc)
    return any(token in message for token in _RECOVERABLE_EVAL_TOKENS)


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
        if recv_timeout <= 0:
            raise ValueError("recv_timeout must be positive")
        healed = False
        while True:
            try:
                return await asyncio.to_thread(
                    self._client.evaluate,
                    self._page,
                    expression,
                    timeout_sec=min(recv_timeout, 120.0),
                )
            except RuntimeError as exc:
                if not healed and is_recoverable_evaluate_error(exc):
                    healed = True
                    message = str(exc)
                    if "No page found" in message or "Target closed" in message:
                        await self.recreate_page()
                    else:
                        await self._heal_detached_page()
                    continue
                raise

    async def recreate_page(self) -> None:
        await asyncio.to_thread(
            self._client.close_page,
            self._page,
            ignore_errors=True,
        )
        self._page = await asyncio.to_thread(
            self._client.new_page,
            self._base_url,
            timeout_ms=120_000,
        )
        await self.wait_shell_ready(timeout_sec=120.0, require_bridge=True)

    async def _heal_detached_page(self) -> None:
        await asyncio.to_thread(
            self._client.navigate,
            self._page,
            self._base_url,
            timeout_ms=60_000,
        )
        await asyncio.sleep(2.0)
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
                timeout_ms=min(int(recv_timeout * 1000), 60_000),
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
