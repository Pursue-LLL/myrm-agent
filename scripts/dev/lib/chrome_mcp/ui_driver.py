"""Semantic real-UI actions over a Chrome DevTools MCP-owned page."""

from __future__ import annotations

from typing import Protocol

from mcp_protocol import text_content
from mcp_snapshot import McpSnapshot, SnapshotNode

_MCP_UI_MIN_TIMEOUT_SEC = 15.0


class McpToolCaller(Protocol):
    def __call__(
        self,
        name: str,
        arguments: dict[str, object],
        *,
        timeout_sec: float | None = None,
    ) -> dict[str, object]: ...


class McpUiDriver:
    """Resolve a fresh semantic UID before every user-visible action."""

    def __init__(self, call_tool: McpToolCaller, page_id: int) -> None:
        self._call_tool = call_tool
        self._page_id = page_id

    def snapshot(self) -> McpSnapshot:
        result = self._call_tool(
            "take_snapshot",
            {"pageId": self._page_id, "verbose": False},
            timeout_sec=_MCP_UI_MIN_TIMEOUT_SEC,
        )
        return McpSnapshot.parse(text_content(result))

    def find(
        self,
        role: str,
        name: str | tuple[str, ...],
        *,
        exact: bool = True,
        enabled: bool = True,
    ) -> SnapshotNode:
        return self.snapshot().find(
            role,
            name,
            exact=exact,
            enabled=enabled,
        )

    def click(
        self,
        role: str,
        name: str | tuple[str, ...],
        *,
        exact: bool = True,
    ) -> None:
        node = self.find(role, name, exact=exact)
        self._call_tool(
            "click",
            {"pageId": self._page_id, "uid": node.uid},
            timeout_sec=_MCP_UI_MIN_TIMEOUT_SEC,
        )

    def fill(
        self,
        role: str,
        name: str | tuple[str, ...],
        value: str,
        *,
        exact: bool = True,
    ) -> None:
        node = self.find(role, name, exact=exact)
        self._call_tool(
            "fill",
            {"pageId": self._page_id, "uid": node.uid, "value": value},
            timeout_sec=_MCP_UI_MIN_TIMEOUT_SEC,
        )

    def wait_for_text(self, *text: str, timeout_ms: int = 5_000) -> None:
        if not text:
            raise ValueError("wait_for_text requires at least one value")
        bounded_timeout = min(max(timeout_ms, 1), 5_000)
        self._call_tool(
            "wait_for",
            {
                "pageId": self._page_id,
                "text": list(text),
                "timeout": bounded_timeout,
            },
            timeout_sec=bounded_timeout / 1000 + 1.0,
        )

