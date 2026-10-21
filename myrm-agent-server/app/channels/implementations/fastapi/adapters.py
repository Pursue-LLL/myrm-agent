"""FastAPI request/response adapters for framework-agnostic route registration.

Implements RequestAdapter and ResponseAdapter protocols for FastAPI,
allowing channels to handle requests/responses without FastAPI dependencies.

[INPUT]
- fastapi::Request, (POS: Out-of-the-box FastAPI implementation. Users can directly use these classes without implementing RouteRegistrar Protocol themselves.)
- app.channels.protocols.adapters::RequestAdapter, (POS: Adapter layer for FastAPI. Converts FastAPI-specific request/response objects to framework-agnostic interfaces defined in the protocols layer.)
- app.channels.protocols.route_registrar::GenericRequest, (POS: Protocol layer for dynamic HTTP route registration. Enables channels to declare their own HTTP endpoints while maintaining framework independence. Business layer implements RouteRegistrar for a specific web framework (e.g. FastAPI via ``myrm-agent-harness[fastapi]``).)

[OUTPUT]
- FastAPIRequestAdapter: Adapts FastAPI Request to GenericRequest
- FastAPIResponseAdapter: Adapts GenericResponse to FastAPI Response

[POS]
Adapter layer for FastAPI. Converts FastAPI-specific request/response objects
to framework-agnostic interfaces defined in the protocols layer.
"""

from __future__ import annotations

from fastapi import Request, Response

from app.channels.protocols.adapters import (
    RequestAdapter,
    ResponseAdapter,
)
from app.channels.protocols.route_registrar import (
    GenericRequest,
    GenericResponse,
)


class _AdaptedRequest:
    """Adapter wrapper for FastAPI Request implementing GenericRequest protocol.

    Transparently forwards all FastAPI Request attributes and methods while
    providing the GenericRequest protocol interface.
    """

    def __init__(self, request: Request) -> None:
        self._request = request

    def __getattr__(self, name: str) -> object:
        """Forward attribute access to underlying FastAPI Request.

        This enables transparent access to all FastAPI Request properties
        and methods (state, url, client, stream, etc.) without explicit wrapping.
        """
        return getattr(self._request, name)

    @property
    def method(self) -> str:
        """HTTP method (GET, POST, etc.)."""
        return self._request.method

    @property
    def path(self) -> str:
        """Request path."""
        return self._request.url.path

    @property
    def headers(self) -> dict[str, str]:
        """Request headers."""
        return dict(self._request.headers)

    @property
    def query_params(self) -> dict[str, str]:
        """Query parameters."""
        return dict(self._request.query_params)

    @property
    def client_ip(self) -> str:
        """Client IP address.

        Returns real client IP, considering X-Forwarded-For and
        X-Real-IP headers for proxied requests.

        Priority:
        1. X-Forwarded-For (first IP in chain)
        2. X-Real-IP (Nginx)
        3. request.client.host (direct connection)
        """
        if forwarded_for := self._request.headers.get("x-forwarded-for"):
            return forwarded_for.split(",")[0].strip()

        if real_ip := self._request.headers.get("x-real-ip"):
            return real_ip.strip()

        if self._request.client:
            return self._request.client.host

        return "unknown"

    async def body(self) -> bytes:
        """Get raw request body."""
        return await self._request.body()

    async def json(self) -> dict[str, object]:
        """Parse request body as JSON."""
        return await self._request.json()


class FastAPIRequestAdapter(RequestAdapter[Request]):
    """Adapts FastAPI Request to GenericRequest.

    Example:
        adapter = FastAPIRequestAdapter()
        generic_request = adapter.adapt(fastapi_request)
        await channel.handle_webhook(generic_request)
    """

    def adapt(self, request: Request) -> GenericRequest:
        """Adapt FastAPI Request to GenericRequest.

        Args:
            request: FastAPI Request object

        Returns:
            GenericRequest protocol-compatible object
        """
        return _AdaptedRequest(request)


class _AdaptedResponse:
    """Adapter wrapper implementing GenericResponse protocol."""

    def __init__(self, status_code: int, headers: dict[str, str], body: bytes) -> None:
        self._status_code = status_code
        self._headers = headers
        self._body = body

    @property
    def status_code(self) -> int:
        """HTTP status code."""
        return self._status_code

    @property
    def headers(self) -> dict[str, str]:
        """Response headers."""
        return self._headers

    @property
    def body(self) -> bytes:
        """Response body."""
        return self._body


class FastAPIResponseAdapter(ResponseAdapter[Response]):
    """Adapts GenericResponse to FastAPI Response.

    Example:
        adapter = FastAPIResponseAdapter()
        generic_response = await channel.handle_webhook(generic_request)
        fastapi_response = adapter.adapt(generic_response)
        return fastapi_response
    """

    def adapt(self, response: GenericResponse) -> Response:
        """Adapt GenericResponse to FastAPI Response.

        Args:
            response: GenericResponse protocol-compatible object

        Returns:
            FastAPI Response object
        """
        return Response(
            content=response.body,
            status_code=response.status_code,
            headers=response.headers,
        )
