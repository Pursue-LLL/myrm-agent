"""Mock and validation utilities for testing channel route registration.

Provides tools for testing channels' register_routes() implementations
without requiring a real web framework.

[INPUT]
- channels.protocols.route_registrar::RouteDefinition, (POS: Protocol layer for dynamic HTTP route registration. Enables channels to declare their own HTTP endpoints while maintaining framework independence. Business layer implements RouteRegistrar for a specific web framework (e.g. FastAPI via ``myrm-agent-harness[fastapi]``).)

[OUTPUT]
- MockRouteRegistrar: Mock registrar for testing
- RouteDefinitionValidator: Validates route definitions for security and correctness

[POS]
Testing layer for route registration. Channels can use MockRouteRegistrar
to verify their route registration logic without a real ASGI/WSGI stack.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from app.channels.protocols.route_registrar import (
    GenericRequest,
    GenericResponse,
    HttpMethod,
    RouteDefinition,
    RouteMetadata,
    RouteSecurityPolicy,
)


class MockRouteRegistrar:
    """Mock registrar for testing channel route registration.

    Collects route registrations in memory for inspection and validation.
    Does not actually register routes with any web framework.

    Example:
        registrar = MockRouteRegistrar()
        channel.register_routes(registrar)

        assert len(registrar.registered_routes) == 2
        assert registrar.get_routes_by_method(HttpMethod.POST) == [...]
        assert registrar.get_route_by_path("webhook") is not None
    """

    def __init__(self) -> None:
        self.registered_routes: list[RouteDefinition] = []

    def add_route(
        self,
        method: HttpMethod,
        path: str,
        handler: Callable[[GenericRequest], Awaitable[GenericResponse]],
        metadata: RouteMetadata | None = None,
    ) -> None:
        """Register a single route (mock implementation).

        Args:
            method: HTTP method
            path: Relative path
            handler: Route handler
            metadata: Optional route metadata
        """
        self.registered_routes.append(
            RouteDefinition(
                method=method,
                path=path,
                handler=handler,
                metadata=metadata or RouteMetadata(),
            )
        )

    def add_routes(self, routes: list[RouteDefinition]) -> None:
        """Register multiple routes at once (mock implementation).

        Args:
            routes: List of route definitions
        """
        self.registered_routes.extend(routes)

    def get_routes_by_method(self, method: HttpMethod) -> list[RouteDefinition]:
        """Get all routes registered with a specific HTTP method.

        Args:
            method: HTTP method to filter by

        Returns:
            List of matching route definitions
        """
        return [r for r in self.registered_routes if r.method == method]

    def get_route_by_path(self, path: str) -> RouteDefinition | None:
        """Get route by exact path match.

        Args:
            path: Path to search for

        Returns:
            Route definition if found, None otherwise
        """
        for route in self.registered_routes:
            if route.path == path:
                return route
        return None

    def get_routes_by_tag(self, tag: str) -> list[RouteDefinition]:
        """Get all routes tagged with a specific tag.

        Args:
            tag: Tag to filter by

        Returns:
            List of matching route definitions
        """
        return [r for r in self.registered_routes if tag in r.metadata.tags]

    def get_routes_requiring_auth(self) -> list[RouteDefinition]:
        """Get all routes that require authentication.

        Returns:
            List of routes with requires_auth=True
        """
        return [r for r in self.registered_routes if r.metadata.requires_auth]

    def get_routes_with_rate_limit(self) -> list[RouteDefinition]:
        """Get all routes with rate limiting policy configured.

        Returns:
            List of routes with rate_limit_policy set
        """
        return [r for r in self.registered_routes if r.metadata.rate_limit_policy is not None]

    def clear(self) -> None:
        """Clear all registered routes."""
        self.registered_routes.clear()


class RouteDefinitionValidator:
    """Validates route definitions for security and correctness.

    Checks for:
    - Invalid paths (contains "..", starts with "/", etc.)
    - Blocked paths
    - Missing required metadata
    - Security policy violations
    """

    @staticmethod
    def validate_path(path: str, policy: RouteSecurityPolicy | None = None) -> list[str]:
        """Validate a route path against security policy.

        Args:
            path: Path to validate
            policy: Optional security policy to enforce

        Returns:
            List of validation error messages (empty if valid)
        """
        errors: list[str] = []

        if not path:
            errors.append("Path cannot be empty")
            return errors

        if path.startswith("/"):
            errors.append("Path must not start with '/' (use relative path)")

        if ".." in path:
            errors.append("Path must not contain '..' (directory traversal)")

        if path.endswith("/"):
            errors.append("Path must not end with '/'")

        if "//" in path:
            errors.append("Path must not contain '//' (double slash)")

        if policy:
            if policy.blocked_paths:
                for blocked in policy.blocked_paths:
                    blocked_clean = blocked.lstrip("/")
                    if blocked_clean and blocked_clean in path:
                        errors.append(f"Path contains blocked pattern: {blocked}")

            if policy.allowed_paths:
                if not any(allowed in path for allowed in policy.allowed_paths):
                    errors.append(f"Path not in allowed list: {policy.allowed_paths}")

        return errors

    @staticmethod
    def validate_route_definition(route: RouteDefinition) -> list[str]:
        """Validate a complete route definition.

        Args:
            route: Route definition to validate

        Returns:
            List of validation error messages (empty if valid)
        """
        errors: list[str] = []

        errors.extend(RouteDefinitionValidator.validate_path(route.path))

        if not route.handler:
            errors.append("Handler cannot be None")

        if route.metadata.rate_limit_policy:
            if route.metadata.rate_limit_policy.max_requests <= 0:
                errors.append("Rate limit max_requests must be positive")
            if route.metadata.rate_limit_policy.window_seconds <= 0:
                errors.append("Rate limit window_seconds must be positive")

        return errors

    @staticmethod
    def validate_route_list(routes: list[RouteDefinition]) -> dict[str, list[str]]:
        """Validate a list of route definitions.

        Args:
            routes: List of route definitions to validate

        Returns:
            Dictionary mapping route path to list of error messages
        """
        errors_by_path: dict[str, list[str]] = {}

        path_counts: dict[str, int] = {}
        for route in routes:
            path_counts[route.path] = path_counts.get(route.path, 0) + 1

        for route in routes:
            route_errors = RouteDefinitionValidator.validate_route_definition(route)

            if path_counts[route.path] > 1:
                route_errors.append(f"Duplicate path: {route.path}")

            if route_errors:
                errors_by_path[route.path] = route_errors

        return errors_by_path
