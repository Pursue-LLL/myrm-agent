"""MCP registry proxy service.

Proxies searches and detail lookups to the Smithery MCP registry,
with LRU caching and rate-limit–friendly timeouts.  Install requests
reuse the existing config_scan + posture pipeline so that every
registry install gets the same 108-pattern security scan.

[INPUT]
- httpx (async HTTP client for external registry)
- app.services.integrations.mcp_posture (security scan integration)

[OUTPUT]
- MCPRegistryService: search / detail / install_config
"""

from __future__ import annotations

import logging
import time
from collections import OrderedDict
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger(__name__)

SMITHERY_BASE_URL = "https://registry.smithery.ai"
DEFAULT_PAGE_SIZE = 20
CACHE_TTL_SECONDS = 300  # 5 minutes
CACHE_MAX_ENTRIES = 100
HTTP_TIMEOUT = 10.0


@dataclass(frozen=True, slots=True)
class RegistryServer:
    """Lightweight representation of a registry server entry."""

    qualified_name: str
    display_name: str
    description: str = ""
    icon_url: str | None = None
    homepage: str | None = None
    use_count: int = 0


@dataclass(frozen=True, slots=True)
class RegistrySearchResult:
    """Paged search result envelope."""

    servers: list[RegistryServer]
    page: int
    page_size: int
    total_pages: int


@dataclass(frozen=True, slots=True)
class RegistryEnvVar:
    """Required environment variable template from registry metadata."""

    name: str
    description: str = ""
    required: bool = True


@dataclass(frozen=True, slots=True)
class RegistryServerDetail:
    """Full detail for a single registry server."""

    qualified_name: str
    display_name: str
    description: str = ""
    icon_url: str | None = None
    homepage: str | None = None
    use_count: int = 0
    transport_type: str = "stdio"
    connections: list[dict] = field(default_factory=list)
    env_vars: list[RegistryEnvVar] = field(default_factory=list)


@dataclass
class _CacheEntry:
    data: object
    expires_at: float


class MCPRegistryService:
    """Async proxy to the Smithery MCP server registry."""

    def __init__(self) -> None:
        self._cache: OrderedDict[str, _CacheEntry] = OrderedDict()

    def _get_cached(self, key: str) -> object | None:
        entry = self._cache.get(key)
        if entry is None:
            return None
        if time.monotonic() > entry.expires_at:
            self._cache.pop(key, None)
            return None
        self._cache.move_to_end(key)
        return entry.data

    def _put_cache(self, key: str, data: object) -> None:
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = _CacheEntry(data=data, expires_at=time.monotonic() + CACHE_TTL_SECONDS)
        while len(self._cache) > CACHE_MAX_ENTRIES:
            self._cache.popitem(last=False)

    async def search(
        self,
        query: str = "",
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> RegistrySearchResult:
        cache_key = f"search:{query}:{page}:{page_size}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached  # type: ignore[return-value]

        params: dict[str, str | int] = {"page": page, "pageSize": page_size}
        if query:
            params["q"] = query

        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            resp = await client.get(f"{SMITHERY_BASE_URL}/api/v1/servers", params=params)
            resp.raise_for_status()
            payload = resp.json()

        servers_raw = payload.get("servers") or []
        servers = [
            RegistryServer(
                qualified_name=s.get("qualifiedName", ""),
                display_name=s.get("displayName", s.get("qualifiedName", "")),
                description=s.get("description", ""),
                icon_url=s.get("iconUrl"),
                homepage=s.get("homepage"),
                use_count=s.get("useCount", 0),
            )
            for s in servers_raw
        ]

        result = RegistrySearchResult(
            servers=servers,
            page=payload.get("page", page),
            page_size=payload.get("pageSize", page_size),
            total_pages=payload.get("totalPages", 1),
        )
        self._put_cache(cache_key, result)
        return result

    async def get_detail(self, qualified_name: str) -> RegistryServerDetail:
        cache_key = f"detail:{qualified_name}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached  # type: ignore[return-value]

        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            resp = await client.get(f"{SMITHERY_BASE_URL}/api/v1/servers/{qualified_name}")
            resp.raise_for_status()
            payload = resp.json()

        connections = payload.get("connections") or []
        transport_type = "stdio"
        if connections:
            first = connections[0]
            transport_type = first.get("type", "stdio")

        env_vars: list[RegistryEnvVar] = []
        for conn in connections:
            config_schema = conn.get("configSchema") or {}
            props = config_schema.get("properties") or {}
            required_set = set(config_schema.get("required") or [])
            for prop_name, prop_info in props.items():
                env_vars.append(
                    RegistryEnvVar(
                        name=prop_name,
                        description=prop_info.get("description", ""),
                        required=prop_name in required_set,
                    )
                )

        detail = RegistryServerDetail(
            qualified_name=payload.get("qualifiedName", qualified_name),
            display_name=payload.get("displayName", qualified_name),
            description=payload.get("description", ""),
            icon_url=payload.get("iconUrl"),
            homepage=payload.get("homepage"),
            use_count=payload.get("useCount", 0),
            transport_type=transport_type,
            connections=connections,
            env_vars=env_vars,
        )
        self._put_cache(cache_key, detail)
        return detail


_registry_instance: MCPRegistryService | None = None


def get_mcp_registry() -> MCPRegistryService:
    """Module-level singleton."""
    global _registry_instance
    if _registry_instance is None:
        _registry_instance = MCPRegistryService()
    return _registry_instance
