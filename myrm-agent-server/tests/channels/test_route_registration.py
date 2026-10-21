"""Unit tests for channel route registration infrastructure.

Tests the RouteRegistrar Protocol, MockRouteRegistrar, and RouteDefinitionValidator.
"""

from __future__ import annotations

import pytest

from app.channels.core import BaseChannel
from app.channels.core.rate_limit import RateLimitConfig
from app.channels.protocols.route_registrar import (
    HttpMethod,
    RouteDefinition,
    RouteMetadata,
    RouteSecurityPolicy,
)
from app.channels.testing.route_testing import (
    MockRouteRegistrar,
    RouteDefinitionValidator,
)


class TestRouteDefinitionValidator:
    """Test RouteDefinitionValidator."""

    def test_valid_path(self):
        """Test validation of valid paths."""
        errors = RouteDefinitionValidator.validate_path("webhook")
        assert errors == []

        errors = RouteDefinitionValidator.validate_path("api/v1/status")
        assert errors == []

    def test_path_with_leading_slash(self):
        """Test that paths with leading slash are invalid."""
        errors = RouteDefinitionValidator.validate_path("/webhook")
        assert "must not start with '/'" in errors[0]

    def test_path_with_double_dot(self):
        """Test that paths with '..' are invalid."""
        errors = RouteDefinitionValidator.validate_path("../webhook")
        assert "must not contain '..'" in errors[0]

    def test_path_with_trailing_slash(self):
        """Test that paths with trailing slash are invalid."""
        errors = RouteDefinitionValidator.validate_path("webhook/")
        assert "must not end with '/'" in errors[0]

    def test_path_with_double_slash(self):
        """Test that paths with '//' are invalid."""
        errors = RouteDefinitionValidator.validate_path("api//webhook")
        assert "must not contain '//'" in errors[0]

    def test_empty_path(self):
        """Test that empty paths are invalid."""
        errors = RouteDefinitionValidator.validate_path("")
        assert "cannot be empty" in errors[0]

    def test_blocked_path(self):
        """Test that blocked paths are detected."""
        policy = RouteSecurityPolicy(blocked_paths=["/admin", "/users"])
        errors = RouteDefinitionValidator.validate_path("admin/delete", policy)
        assert "blocked pattern" in errors[0]

    def test_allowed_path(self):
        """Test that allowed paths are enforced."""
        policy = RouteSecurityPolicy(allowed_paths=["webhook", "status"])
        errors = RouteDefinitionValidator.validate_path("other", policy)
        assert "not in allowed list" in errors[0]

        errors = RouteDefinitionValidator.validate_path("webhook", policy)
        assert errors == []

    def test_validate_route_definition(self):
        """Test validation of complete route definitions."""

        async def handler(req):
            pass

        route = RouteDefinition(
            method=HttpMethod.POST,
            path="webhook",
            handler=handler,
        )
        errors = RouteDefinitionValidator.validate_route_definition(route)
        assert errors == []

    def test_validate_route_with_invalid_rate_limit(self):
        """Test validation of route with invalid rate limit."""

        async def handler(req):
            pass

        route = RouteDefinition(
            method=HttpMethod.POST,
            path="webhook",
            handler=handler,
            metadata=RouteMetadata(rate_limit_policy=RateLimitConfig(max_requests=0, window_seconds=60)),
        )
        errors = RouteDefinitionValidator.validate_route_definition(route)
        assert "max_requests must be positive" in errors[0]

    def test_validate_route_list_with_duplicates(self):
        """Test validation of route list with duplicate paths."""

        async def handler(req):
            pass

        routes = [
            RouteDefinition(HttpMethod.POST, "webhook", handler),
            RouteDefinition(HttpMethod.GET, "webhook", handler),
        ]
        errors_by_path = RouteDefinitionValidator.validate_route_list(routes)
        assert "webhook" in errors_by_path
        assert "Duplicate path" in errors_by_path["webhook"][0]


class TestMockRouteRegistrar:
    """Test MockRouteRegistrar."""

    def test_add_route(self):
        """Test adding a single route."""
        registrar = MockRouteRegistrar()

        async def handler(req):
            pass

        registrar.add_route(HttpMethod.POST, "webhook", handler)

        assert len(registrar.registered_routes) == 1
        assert registrar.registered_routes[0].method == HttpMethod.POST
        assert registrar.registered_routes[0].path == "webhook"
        assert registrar.registered_routes[0].handler == handler

    def test_add_route_with_metadata(self):
        """Test adding a route with metadata."""
        registrar = MockRouteRegistrar()

        async def handler(req):
            pass

        metadata = RouteMetadata(
            description="Test webhook",
            requires_auth=True,
            rate_limit_policy=RateLimitConfig(max_requests=60, window_seconds=60),
            tags=["webhook", "telegram"],
        )
        registrar.add_route(HttpMethod.POST, "webhook", handler, metadata)

        assert len(registrar.registered_routes) == 1
        route = registrar.registered_routes[0]
        assert route.metadata.description == "Test webhook"
        assert route.metadata.requires_auth is True
        assert route.metadata.rate_limit_policy is not None
        assert "telegram" in route.metadata.tags

    def test_add_routes(self):
        """Test adding multiple routes at once."""
        registrar = MockRouteRegistrar()

        async def handler1(req):
            pass

        async def handler2(req):
            pass

        routes = [
            RouteDefinition(HttpMethod.POST, "webhook", handler1),
            RouteDefinition(HttpMethod.GET, "status", handler2),
        ]
        registrar.add_routes(routes)

        assert len(registrar.registered_routes) == 2

    def test_get_routes_by_method(self):
        """Test filtering routes by HTTP method."""
        registrar = MockRouteRegistrar()

        async def handler(req):
            pass

        registrar.add_route(HttpMethod.POST, "webhook", handler)
        registrar.add_route(HttpMethod.GET, "status", handler)
        registrar.add_route(HttpMethod.POST, "callback", handler)

        post_routes = registrar.get_routes_by_method(HttpMethod.POST)
        assert len(post_routes) == 2
        assert all(r.method == HttpMethod.POST for r in post_routes)

        get_routes = registrar.get_routes_by_method(HttpMethod.GET)
        assert len(get_routes) == 1

    def test_get_route_by_path(self):
        """Test getting route by exact path."""
        registrar = MockRouteRegistrar()

        async def handler(req):
            pass

        registrar.add_route(HttpMethod.POST, "webhook", handler)

        route = registrar.get_route_by_path("webhook")
        assert route is not None
        assert route.path == "webhook"

        route = registrar.get_route_by_path("nonexistent")
        assert route is None

    def test_get_routes_by_tag(self):
        """Test filtering routes by tag."""
        registrar = MockRouteRegistrar()

        async def handler(req):
            pass

        registrar.add_route(
            HttpMethod.POST,
            "webhook",
            handler,
            RouteMetadata(tags=["telegram", "webhook"]),
        )
        registrar.add_route(
            HttpMethod.POST,
            "callback",
            handler,
            RouteMetadata(tags=["feishu", "webhook"]),
        )

        webhook_routes = registrar.get_routes_by_tag("webhook")
        assert len(webhook_routes) == 2

        telegram_routes = registrar.get_routes_by_tag("telegram")
        assert len(telegram_routes) == 1

    def test_get_routes_requiring_auth(self):
        """Test filtering routes requiring authentication."""
        registrar = MockRouteRegistrar()

        async def handler(req):
            pass

        registrar.add_route(
            HttpMethod.POST,
            "webhook",
            handler,
            RouteMetadata(requires_auth=False),
        )
        registrar.add_route(
            HttpMethod.GET,
            "private",
            handler,
            RouteMetadata(requires_auth=True),
        )

        auth_routes = registrar.get_routes_requiring_auth()
        assert len(auth_routes) == 1
        assert auth_routes[0].path == "private"

    def test_get_routes_with_rate_limit(self):
        """Test filtering routes with rate limiting."""
        registrar = MockRouteRegistrar()

        async def handler(req):
            pass

        registrar.add_route(HttpMethod.POST, "webhook", handler)
        registrar.add_route(
            HttpMethod.GET,
            "status",
            handler,
            RouteMetadata(rate_limit_policy=RateLimitConfig(max_requests=10, window_seconds=60)),
        )

        limited_routes = registrar.get_routes_with_rate_limit()
        assert len(limited_routes) == 1
        assert limited_routes[0].path == "status"

    def test_clear(self):
        """Test clearing all registered routes."""
        registrar = MockRouteRegistrar()

        async def handler(req):
            pass

        registrar.add_route(HttpMethod.POST, "webhook", handler)
        assert len(registrar.registered_routes) == 1

        registrar.clear()
        assert len(registrar.registered_routes) == 0


class TestChannelRouteRegistration:
    """Test channel route registration integration."""

    def test_channel_register_routes(self):
        """Test that channels can register routes."""

        class TestChannel(BaseChannel):
            name = "test"

            def register_routes(self, registrar: object) -> None:
                from app.channels.protocols import (
                    HttpMethod,
                    RouteMetadata,
                    RouteRegistrar,
                )

                if not isinstance(registrar, RouteRegistrar):
                    return

                async def webhook_handler(req):
                    pass

                registrar.add_route(
                    HttpMethod.POST,
                    "webhook",
                    webhook_handler,
                    RouteMetadata(description="Test webhook"),
                )

            async def send(self, msg):
                pass

        channel = TestChannel()
        registrar = MockRouteRegistrar()

        channel.register_routes(registrar)

        assert len(registrar.registered_routes) == 1
        assert registrar.registered_routes[0].path == "webhook"
        assert registrar.registered_routes[0].metadata.description == "Test webhook"

    def test_channel_without_register_routes(self):
        """Test that channels without register_routes don't break."""

        class MinimalChannel(BaseChannel):
            name = "minimal"

            async def send(self, msg):
                pass

        channel = MinimalChannel()
        registrar = MockRouteRegistrar()

        channel.register_routes(registrar)

        assert len(registrar.registered_routes) == 0


class TestP1Enhancements:
    """Test P1-level enhancements: client_ip and cors_config."""

    def test_route_metadata_with_cors_config(self):
        """Test RouteMetadata with CORS configuration."""
        from app.channels.protocols.route_registrar import (
            CORSConfig,
        )

        cors = CORSConfig(
            allow_origins=["https://example.com"],
            allow_methods=["GET", "POST"],
            allow_headers=["Content-Type", "Authorization"],
            allow_credentials=True,
            max_age=3600,
        )

        metadata = RouteMetadata(
            description="OAuth endpoint",
            cors_config=cors,
        )

        assert metadata.cors_config is not None
        assert metadata.cors_config.allow_origins == ["https://example.com"]
        assert metadata.cors_config.allow_credentials is True
        assert metadata.cors_config.max_age == 3600

    def test_channel_route_with_cors_config(self):
        """Test channel route registration with CORS configuration."""
        from app.channels.protocols.route_registrar import (
            CORSConfig,
        )

        class OAuthChannel(BaseChannel):
            name = "oauth"

            def register_routes(self, registrar: object) -> None:
                from app.channels.protocols import (
                    RouteRegistrar,
                )

                if not isinstance(registrar, RouteRegistrar):
                    return

                async def login_handler(req):
                    pass

                cors = CORSConfig(
                    allow_origins=["https://frontend.com"],
                    allow_credentials=True,
                )

                registrar.add_route(
                    HttpMethod.GET,
                    "login",
                    login_handler,
                    RouteMetadata(
                        description="OAuth login endpoint",
                        cors_config=cors,
                    ),
                )

            async def send(self, msg):
                pass

        channel = OAuthChannel()
        registrar = MockRouteRegistrar()
        channel.register_routes(registrar)

        assert len(registrar.registered_routes) == 1
        route = registrar.registered_routes[0]
        assert route.metadata.cors_config is not None
        assert route.metadata.cors_config.allow_origins == ["https://frontend.com"]

    def test_cors_config_validation_wildcard_with_credentials(self):
        """Test that CORSConfig rejects wildcard origin with credentials."""
        from app.channels.protocols.route_registrar import (
            CORSConfig,
        )

        with pytest.raises(ValueError, match="Cannot use allow_origins="):
            CORSConfig(
                allow_origins=["*"],
                allow_credentials=True,
            )

    def test_cors_config_valid_specific_origin_with_credentials(self):
        """Test that CORSConfig allows specific origin with credentials."""
        from app.channels.protocols.route_registrar import (
            CORSConfig,
        )

        cors = CORSConfig(
            allow_origins=["https://trusted.com"],
            allow_credentials=True,
        )

        assert cors.allow_origins == ["https://trusted.com"]
        assert cors.allow_credentials is True

    def test_cors_config_expose_headers(self):
        """Test CORSConfig expose_headers field."""
        from app.channels.protocols.route_registrar import (
            CORSConfig,
        )

        cors = CORSConfig(
            expose_headers=["X-Rate-Limit-Remaining", "X-Custom-Header"],
        )

        assert cors.expose_headers == ["X-Rate-Limit-Remaining", "X-Custom-Header"]
