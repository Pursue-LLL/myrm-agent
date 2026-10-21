"""FastAPI-specific implementation of RouteRegistrar Protocol.

Implements route registration for FastAPI, including:
- Automatic path prefix enforcement
- Path validation and conflict detection
- Security middleware application
- Rate limiting integration
- Authentication enforcement (via dependency injection)
- Error handling standardization
- OpenAPI documentation generation

[INPUT]
- fastapi::FastAPI, (POS: Out-of-the-box FastAPI implementation. Users can directly use these classes without implementing RouteRegistrar Protocol themselves.)
- app.channels.protocols.route_registrar::RouteRegistrar, (POS: Protocol layer for dynamic HTTP route registration. Enables channels to declare their own HTTP endpoints while maintaining framework independence. Business layer implements RouteRegistrar for a specific web framework (e.g. FastAPI via ``myrm-agent-harness[fastapi]``).)
- app.channels.protocols.rate_limiter::RateLimiterProtocol, (POS: Per-User Rate Limiter for Skill Optimization)
- app.channels.testing.route_testing::RouteDefinitionValidator (POS: Testing layer for route registration. Channels can use MockRouteRegistrar to verify their route registration logic without a real ASGI/WSGI stack.)
- app.channels.implementations.fastapi.adapters::FastAPIRequestAdapter, (POS: Adapter layer for FastAPI. Converts FastAPI-specific request/response objects to framework-agnostic interfaces defined in the protocols layer.)

[OUTPUT]
- FastAPIRouteRegistrar: FastAPI implementation of RouteRegistrar Protocol

[POS]
Framework-layer implementation of route registration for FastAPI. Enforces
security policies, applies middleware, and manages route lifecycle. Business
layer injects authentication dependency via auth_dependency parameter.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.channels.implementations.fastapi.adapters import (
    FastAPIRequestAdapter,
    FastAPIResponseAdapter,
)
from app.channels.protocols.rate_limiter import (
    NoOpRateLimiter,
    RateLimiterProtocol,
)
from app.channels.protocols.route_registrar import (
    GenericRequest,
    GenericResponse,
    HttpMethod,
    RouteDefinition,
    RouteMetadata,
    RouteSecurityPolicy,
)
from app.channels.testing.route_testing import (
    RouteDefinitionValidator,
)

logger = logging.getLogger(__name__)


class FastAPIRouteRegistrar:
    """FastAPI-specific implementation of RouteRegistrar Protocol.

    Implements route registration with:
    - Automatic path prefix: /api/channels/{channel_name}/{path}
    - Path validation and conflict detection
    - Security middleware application
    - Rate limiting integration
    - Error handling standardization
    - OpenAPI documentation generation

    Example:
        from fastapi import Depends

        app = FastAPI()
        policy = RouteSecurityPolicy(
            enforce_prefix=True,
            blocked_paths=["/admin", "/api/users"],
        )
        registrar = FastAPIRouteRegistrar(
            app=app,
            channel_name="telegram",
            security_policy=policy,
            auth_dependency=Depends(get_current_user_id),  # Injected from business layer
        )
        channel.register_routes(registrar)
    """

    def __init__(
        self,
        app: FastAPI,
        channel_name: str,
        security_policy: RouteSecurityPolicy | None = None,
        apply_middleware: bool = True,
        rate_limiter: RateLimiterProtocol | None = None,
        auth_dependency: object | None = None,
    ) -> None:
        """Initialize FastAPI route registrar.

        Args:
            app: FastAPI application instance
            channel_name: Name of the channel registering routes
            security_policy: Optional security policy for path validation
            apply_middleware: Whether to automatically apply middleware
            rate_limiter: Rate limiting implementation (defaults to NoOpRateLimiter
                for Agent-in-Sandbox architecture)
            auth_dependency: Optional FastAPI dependency for authentication
                (e.g., Depends(get_current_user_id)). If None, authenticated
                routes will not enforce authentication.
        """
        self.app = app
        self.channel_name = channel_name
        self.security_policy = security_policy or RouteSecurityPolicy()
        self.apply_middleware = apply_middleware
        self.rate_limiter = rate_limiter or NoOpRateLimiter()
        self.auth_dependency = auth_dependency
        self.registered_paths: set[str] = set()
        self.request_adapter = FastAPIRequestAdapter()
        self.response_adapter = FastAPIResponseAdapter()

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
            handler: Async handler function accepting GenericRequest
            metadata: Optional route metadata for documentation and configuration

        Raises:
            ValueError: If path validation fails or path already registered
        """
        meta = metadata or RouteMetadata()

        errors = RouteDefinitionValidator.validate_path(path, self.security_policy)
        if errors:
            raise ValueError(f"Invalid route path '{path}': {', '.join(errors)}")

        full_path = f"/api/channels/{self.channel_name}/{path}"

        if full_path in self.registered_paths:
            raise ValueError(f"Route already registered: {full_path}")

        wrapped_handler = self._wrap_handler(handler, meta)

        self.app.add_api_route(
            full_path,
            wrapped_handler,
            methods=[method.value],
            tags=[f"channel-{self.channel_name}"],
            description=meta.description,
            deprecated=meta.deprecated,
        )

        self.registered_paths.add(full_path)
        logger.info(
            "Registered channel route",
            extra={
                "channel": self.channel_name,
                "method": method.value,
                "path": full_path,
                "requires_auth": meta.requires_auth,
                "has_rate_limit": meta.rate_limit_policy is not None,
                "has_cors": meta.cors_config is not None,
            },
        )

        if meta.cors_config:
            self._register_options_handler(full_path, meta.cors_config)

    def add_routes(self, routes: list[RouteDefinition]) -> None:
        """Register multiple routes at once.

        Args:
            routes: List of route definitions to register
        """
        for route in routes:
            self.add_route(
                route.method,
                route.path,
                route.handler,
                route.metadata,
            )

    def _register_options_handler(self, full_path: str, cors_config: object) -> None:
        """Register OPTIONS preflight handler for CORS.

        Args:
            full_path: Full route path
            cors_config: CORSConfig object with CORS settings
        """

        async def options_handler(request: Request):
            """Handle CORS preflight OPTIONS request."""
            from fastapi.responses import Response

            response = Response(status_code=204)
            self._apply_cors_headers(response, cors_config, request)
            return response

        self.app.add_api_route(
            full_path,
            options_handler,
            methods=["OPTIONS"],
            tags=[f"channel-{self.channel_name}"],
            description="CORS preflight handler",
            include_in_schema=False,
        )

        logger.debug(
            "Registered OPTIONS handler for CORS",
            extra={"channel": self.channel_name, "path": full_path},
        )

    def _apply_cors_headers(self, response: JSONResponse, cors_config: object, request: Request) -> None:
        """Apply CORS headers to response.

        CRITICAL: Access-Control-Allow-Origin does NOT support comma-separated
        multiple origins. Must check request Origin header and return single
        matching origin or "*".

        Args:
            response: FastAPI JSONResponse to modify
            cors_config: CORSConfig object with CORS settings
            request: FastAPI Request to get Origin header
        """
        from app.channels.protocols.route_registrar import (
            CORSConfig,
        )

        if not isinstance(cors_config, CORSConfig):
            return

        origin = request.headers.get("origin", "")

        if "*" in cors_config.allow_origins:
            response.headers["Access-Control-Allow-Origin"] = "*"
        elif origin and origin in cors_config.allow_origins:
            response.headers["Access-Control-Allow-Origin"] = origin
        else:
            return

        response.headers["Access-Control-Allow-Methods"] = ", ".join(cors_config.allow_methods)
        response.headers["Access-Control-Allow-Headers"] = ", ".join(cors_config.allow_headers)

        if cors_config.expose_headers:
            response.headers["Access-Control-Expose-Headers"] = ", ".join(cors_config.expose_headers)

        if cors_config.allow_credentials:
            response.headers["Access-Control-Allow-Credentials"] = "true"

        response.headers["Access-Control-Max-Age"] = str(cors_config.max_age)

    def _wrap_handler(
        self,
        handler: Callable[[GenericRequest], Awaitable[GenericResponse]],
        metadata: RouteMetadata,
    ) -> Callable:
        """Wrap handler with adapters, middleware, and error handling.

        Args:
            handler: Original generic handler
            metadata: Route metadata for middleware configuration

        Returns:
            FastAPI-compatible handler function
        """

        if metadata.requires_auth and self.auth_dependency is not None:

            async def wrapped(request: Request, user_id: str = self.auth_dependency):
                import time

                start_time = time.monotonic()

                if metadata.required_permissions and self.permission_checker:
                    has_permission = await self.permission_checker(user_id, metadata.required_permissions)
                    if not has_permission:
                        latency_ms = (time.monotonic() - start_time) * 1000
                        self.metrics.record_request(
                            route_path=request.url.path,
                            method=request.method,
                            status_code=403,
                            latency_ms=latency_ms,
                            error="Insufficient permissions",
                        )

                        error_response = JSONResponse(
                            {"error": "Forbidden: Insufficient permissions"},
                            status_code=403,
                        )

                        if metadata.cors_config:
                            self._apply_cors_headers(error_response, metadata.cors_config, request)

                        return error_response

                if metadata.rate_limit_policy:
                    allowed, remaining = await self.rate_limiter.check_limit(
                        route_path=request.url.path,
                        client_id=user_id,
                        limit_config=metadata.rate_limit_policy,
                    )

                    if not allowed:
                        latency_ms = (time.monotonic() - start_time) * 1000
                        self.metrics.record_request(
                            route_path=request.url.path,
                            method=request.method,
                            status_code=429,
                            latency_ms=latency_ms,
                            error="Rate limit exceeded",
                        )

                        error_response = JSONResponse(
                            {"error": "Rate limit exceeded"},
                            status_code=429,
                            headers={"X-RateLimit-Remaining": "0"},
                        )

                        if metadata.cors_config:
                            self._apply_cors_headers(error_response, metadata.cors_config, request)

                        return error_response

                try:
                    generic_request = self.request_adapter.adapt(request)
                    generic_response = await handler(generic_request)
                    fastapi_response = self.response_adapter.adapt(generic_response)

                    latency_ms = (time.monotonic() - start_time) * 1000
                    self.metrics.record_request(
                        route_path=request.url.path,
                        method=request.method,
                        status_code=generic_response.status_code,
                        latency_ms=latency_ms,
                    )

                    if metadata.cors_config:
                        self._apply_cors_headers(fastapi_response, metadata.cors_config, request)

                    return fastapi_response
                except Exception as e:
                    latency_ms = (time.monotonic() - start_time) * 1000
                    self.metrics.record_request(
                        route_path=request.url.path,
                        method=request.method,
                        status_code=500,
                        latency_ms=latency_ms,
                        error=str(e),
                    )

                    logger.error(
                        "Channel route handler error",
                        extra={
                            "channel": self.channel_name,
                            "path": request.url.path,
                            "user_id": user_id,
                            "error": str(e),
                        },
                        exc_info=True,
                    )
                    error_response = JSONResponse(
                        {"error": "Internal server error"},
                        status_code=500,
                    )

                    if metadata.cors_config:
                        self._apply_cors_headers(error_response, metadata.cors_config, request)

                    return error_response

        else:

            async def wrapped(request: Request):
                import time

                start_time = time.monotonic()

                if metadata.rate_limit_policy:
                    client_id = request.client.host if request.client else "unknown"
                    allowed, remaining = await self.rate_limiter.check_limit(
                        route_path=request.url.path,
                        client_id=client_id,
                        limit_config=metadata.rate_limit_policy,
                    )

                    if not allowed:
                        latency_ms = (time.monotonic() - start_time) * 1000
                        self.metrics.record_request(
                            route_path=request.url.path,
                            method=request.method,
                            status_code=429,
                            latency_ms=latency_ms,
                            error="Rate limit exceeded",
                        )

                        error_response = JSONResponse(
                            {"error": "Rate limit exceeded"},
                            status_code=429,
                            headers={"X-RateLimit-Remaining": "0"},
                        )

                        if metadata.cors_config:
                            self._apply_cors_headers(error_response, metadata.cors_config, request)

                        return error_response

                try:
                    generic_request = self.request_adapter.adapt(request)
                    generic_response = await handler(generic_request)
                    fastapi_response = self.response_adapter.adapt(generic_response)

                    latency_ms = (time.monotonic() - start_time) * 1000
                    self.metrics.record_request(
                        route_path=request.url.path,
                        method=request.method,
                        status_code=generic_response.status_code,
                        latency_ms=latency_ms,
                    )

                    if metadata.cors_config:
                        self._apply_cors_headers(fastapi_response, metadata.cors_config, request)

                    return fastapi_response
                except Exception as e:
                    latency_ms = (time.monotonic() - start_time) * 1000
                    self.metrics.record_request(
                        route_path=request.url.path,
                        method=request.method,
                        status_code=500,
                        latency_ms=latency_ms,
                        error=str(e),
                    )

                    logger.error(
                        "Channel route handler error",
                        extra={
                            "channel": self.channel_name,
                            "path": request.url.path,
                            "error": str(e),
                        },
                        exc_info=True,
                    )
                    error_response = JSONResponse(
                        {"error": "Internal server error"},
                        status_code=500,
                    )

                    if metadata.cors_config:
                        self._apply_cors_headers(error_response, metadata.cors_config, request)

                    return error_response

        return wrapped
