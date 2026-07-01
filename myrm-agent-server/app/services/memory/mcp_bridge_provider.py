"""MCPBridgeProvider — bridges any MCP Server as an IntegrationProvider.

[INPUT]
- myrm_agent_harness.toolkits.mcp.connection_manager (POS: MCP persistent session pool)
- myrm_agent_harness.api::IntegrationProvider (POS: IntegrationProvider Protocol)

[OUTPUT]
- MCPBridgeProvider: Concrete IntegrationProvider that fetches data via MCP tool calls.

[POS]
Turns any MCP Server into an IntegrationProvider by introspecting its tool
catalog and invoking search/list/read tools to pull data.  This avoids
hardcoding per-service integrations (Notion, Google Drive, etc.) and instead
leverages the user's already-configured MCP Servers as knowledge sources.

The MCPConnection is injected at construction time (by the service that
creates MCPBridgeProvider instances) so the provider never reaches into
global singletons — pure dependency injection.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from myrm_agent_harness.api import IntegrationProvider
from myrm_agent_harness.toolkits.memory.integration.types import IntegrationLeaf

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.mcp.connection_manager import MCPConnection

logger = logging.getLogger(__name__)

_MIN_CONTENT_LENGTH = 20

_FETCH_TOOL_PATTERNS = (
    "search",
    "list",
    "query",
    "get_all",
    "read",
    "fetch",
    "find",
)

_CONSUMED_LEAF_KEYS = frozenset({
    "title", "name", "content", "text", "body",
    "description", "snippet", "id", "type", "object", "kind",
})

_SINCE_PARAM_NAMES = (
    "since", "after", "updated_since", "modified_after",
    "from_date", "start_date", "cursor",
)


class MCPBridgeProvider(IntegrationProvider):
    """Bridges an MCP Server as an IntegrationProvider for knowledge sync.

    Strategy:
    1. Receive an already-established MCPConnection via DI.
    2. Introspect the server's tool catalog and auto-detect the best fetch tool.
    3. On each sync, call that tool and convert results to IntegrationLeaf.
    """

    def __init__(
        self,
        server_name: str,
        connection: MCPConnection,
        display: str = "",
        *,
        fetch_tool_name: str = "",
        fetch_tool_params: dict[str, object] | None = None,
    ) -> None:
        self._server_name = server_name
        self._conn = connection
        self._display = display or server_name
        self._fetch_tool_name = fetch_tool_name
        self._fetch_tool_params = fetch_tool_params or {}
        self._last_sync_cursor: str | None = None

    @property
    def provider_id(self) -> str:
        return f"mcp:{self._server_name}"

    @property
    def display_name(self) -> str:
        return self._display

    async def fetch(
        self,
        *,
        account_key: str = "",
        since_cursor: str | None = None,
        max_items: int = 200,
    ) -> list[IntegrationLeaf]:
        tool_name = self._fetch_tool_name
        if not tool_name:
            tool_name = self._detect_fetch_tool()
            if not tool_name:
                logger.warning("No suitable fetch tool found for MCP server '%s'", self._server_name)
                return []
            self._fetch_tool_name = tool_name

        params = dict(self._fetch_tool_params)
        if max_items and "limit" not in params:
            params["limit"] = max_items

        if since_cursor:
            self._inject_since_cursor(params, since_cursor)

        try:
            raw_result = await self._conn.call(self._server_name, tool_name, params)
        except Exception as exc:
            logger.error("MCP fetch failed: server=%s tool=%s error=%s", self._server_name, tool_name, exc)
            return []

        leaves = self._parse_results(raw_result, max_items)
        if leaves:
            self._last_sync_cursor = datetime.now(UTC).isoformat()
        return leaves

    async def get_sync_cursor(self, *, account_key: str = "") -> str | None:
        return self._last_sync_cursor

    async def validate_connection(self, *, account_key: str = "") -> bool:
        return await self._conn.health_check()

    # ── Internal ─────────────────────────────────────────────────────

    def _inject_since_cursor(self, params: dict[str, object], since_cursor: str) -> None:
        """Inject since_cursor into params if the tool schema accepts a time filter.

        Inspects the detected tool's input schema for common incremental-fetch
        parameter names (since, after, updated_since, etc.) and injects the
        cursor value when found.  Falls back to full-fetch if no such parameter
        exists — correctness is guaranteed by IntegrationFetcher's dedup layer.
        """
        try:
            server_tools = self._conn.tools_by_server.get(self._server_name, [])
            for tool in server_tools:
                if tool.name != self._fetch_tool_name:
                    continue
                schema = getattr(tool, "args_schema", None)
                if schema is None:
                    break
                schema_fields = set(schema.model_fields) if hasattr(schema, "model_fields") else set()
                if not schema_fields:
                    schema_props = getattr(schema, "schema", lambda: {})()
                    schema_fields = set(schema_props.get("properties", {}))
                for param_name in _SINCE_PARAM_NAMES:
                    if param_name in schema_fields:
                        params[param_name] = since_cursor
                        return
                break
        except Exception:
            pass

    def _detect_fetch_tool(self) -> str:
        """Introspect MCP server tools and pick the best fetch tool."""
        try:
            server_tools = self._conn.tools_by_server.get(self._server_name, [])
            if not server_tools:
                return ""

            tool_names = [t.name for t in server_tools]
            for pattern in _FETCH_TOOL_PATTERNS:
                for name in tool_names:
                    if pattern in name.lower():
                        logger.info("Auto-detected fetch tool '%s' for MCP server '%s'", name, self._server_name)
                        return name
        except Exception as exc:
            logger.warning("Failed to detect fetch tool for '%s': %s", self._server_name, exc)
        return ""

    def _parse_results(self, raw: object, max_items: int) -> list[IntegrationLeaf]:
        """Convert MCP tool call results to IntegrationLeaf records."""
        items: list[dict[str, object]] = []

        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
            except (json.JSONDecodeError, ValueError):
                if len(raw) >= _MIN_CONTENT_LENGTH:
                    return [
                        IntegrationLeaf(
                            provider=self.provider_id,
                            source_type="document",
                            title=f"Content from {self._server_name}",
                            content=raw[:50000],
                            external_object_id=f"{self._server_name}::raw::{hash(raw) & 0xFFFFFFFF:08x}",
                        )
                    ]
                return []
            raw = parsed

        if isinstance(raw, list):
            items = [item for item in raw if isinstance(item, dict)]
        elif isinstance(raw, dict):
            for key in ("results", "items", "data", "pages", "documents", "entries"):
                if key in raw and isinstance(raw[key], list):
                    items = [item for item in raw[key] if isinstance(item, dict)]
                    break
            if not items:
                items = [raw]

        leaves: list[IntegrationLeaf] = []
        for item in items[:max_items]:
            leaf = self._item_to_leaf(item)
            if leaf is not None:
                leaves.append(leaf)
        return leaves

    def _item_to_leaf(self, item: dict[str, object]) -> IntegrationLeaf | None:
        """Convert a single result item dict to an IntegrationLeaf."""
        title = str(item.get("title") or item.get("name") or item.get("subject") or "")
        content = str(
            item.get("content")
            or item.get("text")
            or item.get("body")
            or item.get("description")
            or item.get("snippet")
            or "",
        )

        if len(title) + len(content) < _MIN_CONTENT_LENGTH:
            return None

        ext_id = str(item.get("id") or item.get("url") or item.get("uri") or item.get("external_id") or "")
        source_type = str(item.get("type") or item.get("object") or item.get("kind") or "document")

        safe_metadata: dict[str, str | int | float | bool] = {}
        for k, v in item.items():
            if k in _CONSUMED_LEAF_KEYS:
                continue
            if isinstance(v, (str, int, float, bool)):
                safe_metadata[k] = v

        return IntegrationLeaf(
            provider=self.provider_id,
            source_type=source_type,
            external_object_id=ext_id,
            title=title[:500],
            content=content[:50000],
            metadata=safe_metadata,
        )
