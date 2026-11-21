"""Layer 1: the context route that aborts requests the allowlist, the blocklist or the document rule refuses."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from unittest.mock import AsyncMock, MagicMock

import pytest
from patchright.async_api import Route

from myrm_agent_harness.toolkits.browser.domain_filter import DomainAllowlist

_RouteHandler = Callable[[Route], Awaitable[None]]


@pytest.mark.asyncio
async def test_http_filter_blocks_non_allowed_domain() -> None:
    """Test HTTP filter blocks requests to non-allowed domains."""
    from myrm_agent_harness.toolkits.browser.domain_filter import _install_http_filter

    context = MagicMock()
    route_handler: _RouteHandler | None = None

    async def capture_handler(pattern: str, handler: _RouteHandler) -> None:
        nonlocal route_handler
        route_handler = handler

    context.route = capture_handler

    allowlist = DomainAllowlist(patterns=("example.com",))
    await _install_http_filter(context, allowlist)

    assert route_handler is not None

    mock_route = MagicMock()
    mock_route.request.url = "https://blocked.com/path"
    mock_route.request.resource_type = "document"
    mock_route.abort = AsyncMock()
    mock_route.fallback = AsyncMock()

    await route_handler(mock_route)

    mock_route.abort.assert_called_once_with("blockedbyclient")
    mock_route.fallback.assert_not_called()


@pytest.mark.asyncio
async def test_http_filter_allows_allowed_domain() -> None:
    """Test HTTP filter allows requests to allowed domains."""
    from myrm_agent_harness.toolkits.browser.domain_filter import _install_http_filter

    context = MagicMock()
    route_handler: _RouteHandler | None = None

    async def capture_handler(pattern: str, handler: _RouteHandler) -> None:
        nonlocal route_handler
        route_handler = handler

    context.route = capture_handler

    allowlist = DomainAllowlist(patterns=("example.com",))
    await _install_http_filter(context, allowlist)

    assert route_handler is not None
    mock_route = MagicMock()
    mock_route.request.url = "https://example.com/path"
    mock_route.request.resource_type = "document"
    mock_route.abort = AsyncMock()
    mock_route.fallback = AsyncMock()

    await route_handler(mock_route)

    mock_route.fallback.assert_called_once()
    mock_route.abort.assert_not_called()


@pytest.mark.asyncio
async def test_http_filter_non_http_document_blocked() -> None:
    """Test HTTP filter blocks non-HTTP document resources."""
    from myrm_agent_harness.toolkits.browser.domain_filter import _install_http_filter

    context = MagicMock()
    route_handler: _RouteHandler | None = None

    async def capture_handler(pattern: str, handler: _RouteHandler) -> None:
        nonlocal route_handler
        route_handler = handler

    context.route = capture_handler

    allowlist = DomainAllowlist(patterns=("example.com",))
    await _install_http_filter(context, allowlist)

    assert route_handler is not None
    mock_route = MagicMock()
    mock_route.request.url = "chrome://version"
    mock_route.request.resource_type = "document"
    mock_route.abort = AsyncMock()
    mock_route.fallback = AsyncMock()

    await route_handler(mock_route)

    mock_route.abort.assert_called_once_with("blockedbyclient")


@pytest.mark.asyncio
async def test_http_filter_blocks_domain_blocklist_before_allowlist() -> None:
    """Blocklist denies even when hostname would pass allowlist."""
    from myrm_agent_harness.toolkits.browser.domain_filter import _install_http_filter

    context = MagicMock()
    route_handler: _RouteHandler | None = None

    async def capture_handler(pattern: str, handler: _RouteHandler) -> None:
        nonlocal route_handler
        route_handler = handler

    context.route = capture_handler

    allowlist = DomainAllowlist(patterns=("example.com",))
    blocklist = DomainAllowlist.from_strings(["blocked.com"])
    await _install_http_filter(context, allowlist, domain_blocklist=blocklist)

    assert route_handler is not None
    mock_route = MagicMock()
    mock_route.request.url = "https://blocked.com/path"
    mock_route.request.resource_type = "document"
    mock_route.abort = AsyncMock()
    mock_route.fallback = AsyncMock()

    await route_handler(mock_route)

    mock_route.abort.assert_called_once_with("blockedbyclient")
    mock_route.fallback.assert_not_called()


@pytest.mark.asyncio
async def test_http_filter_non_http_non_document_allowed() -> None:
    """Test HTTP filter allows non-HTTP non-document resources."""
    from myrm_agent_harness.toolkits.browser.domain_filter import _install_http_filter

    context = MagicMock()
    route_handler: _RouteHandler | None = None

    async def capture_handler(pattern: str, handler: _RouteHandler) -> None:
        nonlocal route_handler
        route_handler = handler

    context.route = capture_handler

    allowlist = DomainAllowlist(patterns=("example.com",))
    await _install_http_filter(context, allowlist)

    assert route_handler is not None
    mock_route = MagicMock()
    mock_route.request.url = "data:text/html,<h1>Test</h1>"
    mock_route.request.resource_type = "image"
    mock_route.abort = AsyncMock()
    mock_route.fallback = AsyncMock()

    await route_handler(mock_route)

    mock_route.fallback.assert_called_once()
