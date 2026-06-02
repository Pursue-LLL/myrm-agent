"""HTTP route registration protocol for custom channel endpoints.

Provides framework-agnostic interfaces for channels to register their own
HTTP endpoints (webhooks, login pages, status endpoints) without coupling
to a specific web framework.

[INPUT]
- channels.core.rate_limit::RateLimitConfig (POS: rate limiting configuration)

[OUTPUT]
- RouteRegistrar Protocol: Framework-agnostic route registration interface
- RouteDefinition: Route metadata dataclass
- RouteMetadata: Route documentation and configuration
- RouteSecurityPolicy: Security constraints for route registration
- HttpMethod: HTTP method enumeration
- GenericRequest/GenericResponse: Framework-agnostic request/response protocols

[POS]
Protocol layer for dynamic HTTP route registration. Enables channels to declare
their own HTTP endpoints while maintaining framework independence. Business layer
implements RouteRegistrar for a specific web framework (e.g. FastAPI via
``myrm-agent-harness[fastapi]``).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol, runtime_checkable

from app.channels.core.rate_limit import RateLimitConfig


class HttpMethod(Enum):
    """HTTP methods supported by route registration."""

    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"
    PATCH = "PATCH"


@dataclass(frozen=True, slots=True)
class CORSConfig:
    """CORS configuration for individual routes.

    Allows channels to define custom CORS policies for their endpoints,
    enabling frontend applications to call channel endpoints directly
    (e.g., OAuth login pages, WeChat scan QR code endpoints).

    Security: Only apply CORS to endpoints that truly need cross-origin
    access. Most webhook endpoints should NOT enable CORS.

    CRITICAL: Cannot use allow_origins=["*"] with allow_credentials=True.
    Browsers will reject this combination per CORS specification.
    """

    allow_origins: list[str] = field(default_factory=lambda: ["*"])
    allow_methods: list[str] = field(default_factory=lambda: ["GET", "POST"])
    allow_headers: list[str] = field(default_factory=lambda: ["*"])
    expose_headers: list[str] = field(default_factory=list)
    allow_credentials: bool = False
    max_age: int = 600

    def __post_init__(self) -> None:
        """Validate CORS configuration.

        Raises:
            ValueError: If configuration violates CORS specification
        """
        if self.allow_credentials and "*" in self.allow_origins:
            raise ValueError(
                "CORS configuration error: Cannot use allow_origins=['*'] with "
                "allow_credentials=True. Browsers will reject this combination. "
                "Specify explicit origins instead."
            )


@dataclass(frozen=True, slots=True)
class RouteMetadata:
    """Metadata for route registration.

    Provides information for API documentation, authentication,
    rate limiting policy, CORS configuration, and deprecation tracking.

    Rate Limiting Policy (Agent-in-Sandbox Architecture):
        The rate_limit_policy field declares the desired rate limiting
        strategy for this route. Actual enforcement depends on deployment:
        - Agent-in-Sandbox (default): NoOpRateLimiter (single-user sandbox)
        - Multi-user Server: InMemoryRateLimiter or RedisRateLimiter
        - Control plane: IP-based rate limiting at webhook entry

        Business layer injects appropriate RateLimiterProtocol implementation
        into RouteRegistrar based on deployment mode.

    Permission Control (RBAC Support):
        The required_permissions field enables fine-grained access control.
        Business layer should check user permissions before allowing access.
        Example: required_permissions=["channel:write", "admin"] means user
        needs BOTH permissions to access this route.
    """

    description: str = ""
    requires_auth: bool = False
    required_permissions: list[str] = field(default_factory=list)
    rate_limit_policy: RateLimitConfig | None = None
    cors_config: CORSConfig | None = None
    tags: list[str] = field(default_factory=list)
    deprecated: bool = False


@dataclass(frozen=True, slots=True)
class RouteSecurityPolicy:
    """Security policy for route registration.

    Enforces constraints on route paths to prevent security issues
    (path conflicts, malicious routes, middleware bypass).
    """

    enforce_prefix: bool = True
    allowed_paths: list[str] = field(default_factory=list)
    blocked_paths: list[str] = field(default_factory=list)


class GenericRequest(Protocol):
    """Framework-agnostic request interface.

    Allows channels to handle requests without depending on
    framework-specific request objects.
    """

    @property
    def method(self) -> str:
        """HTTP method (GET, POST, etc.)."""
        ...

    @property
    def path(self) -> str:
        """Request path."""
        ...

    @property
    def headers(self) -> dict[str, str]:
        """Request headers."""
        ...

    @property
    def query_params(self) -> dict[str, str]:
        """Query parameters."""
        ...

    @property
    def client_ip(self) -> str:
        """Client IP address.

        Returns real client IP, considering X-Forwarded-For and
        X-Real-IP headers for proxied requests.

        Security: Used for IP whitelist validation, rate limiting,
        and audit logging. More reliable than manual header parsing.
        """
        ...

    async def body(self) -> bytes:
        """Get raw request body."""
        ...

    async def json(self) -> dict[str, object]:
        """Parse request body as JSON."""
        ...


class GenericResponse(Protocol):
    """Framework-agnostic response interface.

    Allows channels to return responses without depending on
    framework-specific response objects.
    """

    @property
    def status_code(self) -> int:
        """HTTP status code."""
        ...

    @property
    def headers(self) -> dict[str, str]:
        """Response headers."""
        ...

    @property
    def body(self) -> bytes:
        """Response body."""
        ...


@dataclass(frozen=True, slots=True)
class RouteDefinition:
    """Complete route definition for registration.

    Combines method, path, handler, and metadata into a single
    unit for bulk route registration.
    """

    method: HttpMethod
    path: str
    handler: Callable[[GenericRequest], Awaitable[GenericResponse]]
    metadata: RouteMetadata = field(default_factory=RouteMetadata)


@runtime_checkable
class RouteRegistrar(Protocol):
    """Protocol for registering HTTP routes.

    Framework-agnostic interface that allows channels to register
    their own HTTP endpoints without coupling to a specific web framework.

    Business layer implements this protocol for specific web frameworks.
    Framework layer (BaseChannel) calls these methods to register routes.

    Security enforcement:
    - Automatic path prefix (e.g., /api/channels/{channel_name}/)
    - Path validation (no "..", no leading "/")
    - Blocked path checking
    - Automatic middleware application (security, rate limiting)

    Example:
        class TelegramChannel(BaseChannel):
            def register_routes(self, registrar: RouteRegistrar):
                registrar.add_route(
                    HttpMethod.POST,
                    "webhook",
                    self._handle_webhook,
                    RouteMetadata(
                        description="Receive Telegram webhook updates",
                        rate_limit=RateLimitConfig(max_requests=60, window_seconds=60),
                    ),
                )
    """

    def add_route(
        self,
        method: HttpMethod,
        path: str,
        handler: Callable[[GenericRequest], Awaitable[GenericResponse]],
        metadata: RouteMetadata | None = None,
    ) -> None:
        """Register a single HTTP route.

        Args:
            method: HTTP method (GET, POST, etc.)
            path: Relative path without leading slash (e.g., "webhook", "login")
                  Full path will be: /api/channels/{channel_name}/{path}
            handler: Async handler function accepting GenericRequest and returning GenericResponse
            metadata: Optional route metadata for documentation and configuration

        Raises:
            ValueError: If path validation fails (contains "..", starts with "/", blocked path)
        """
        ...

    def add_routes(self, routes: list[RouteDefinition]) -> None:
        """Register multiple routes at once.

        Args:
            routes: List of route definitions to register
        """
        ...
