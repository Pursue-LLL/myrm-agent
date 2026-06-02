"""Unit tests for FastAPIRouteRegistrar."""

from __future__ import annotations

import pytest
from fastapi import FastAPI

from app.channels.implementations.fastapi.registrar import (
    FastAPIRouteRegistrar,
)
from app.channels.protocols.rate_limiter import (
    NoOpRateLimiter,
)
from app.channels.protocols.route_registrar import (
    HttpMethod,
    RouteMetadata,
    RouteSecurityPolicy,
)


@pytest.fixture
def app():
    """Create a FastAPI app."""
    return FastAPI()


@pytest.fixture
def registrar(app):
    """Create a FastAPIRouteRegistrar."""
    return FastAPIRouteRegistrar(
        app=app,
        channel_name="test",
        security_policy=RouteSecurityPolicy(),
        rate_limiter=NoOpRateLimiter(),
    )


class TestFastAPIRouteRegistrar:
    """Test FastAPIRouteRegistrar."""

    def test_initialization(self, app):
        """Test registrar initialization."""
        registrar = FastAPIRouteRegistrar(
            app=app,
            channel_name="telegram",
        )
        assert registrar.app == app
        assert registrar.channel_name == "telegram"
        assert isinstance(registrar.rate_limiter, NoOpRateLimiter)

    def test_add_route(self, registrar):
        """Test adding a simple route."""

        async def handler(request):
            class Response:
                status_code = 200
                headers = {}
                body = b"ok"

            return Response()

        registrar.add_route(
            method=HttpMethod.POST,
            path="webhook",
            handler=handler,
        )

        assert "/api/channels/test/webhook" in registrar.registered_paths

    def test_add_route_with_metadata(self, registrar):
        """Test adding a route with metadata."""

        async def handler(request):
            class Response:
                status_code = 200
                headers = {}
                body = b"ok"

            return Response()

        metadata = RouteMetadata(
            description="Test webhook endpoint",
            requires_auth=False,
        )

        registrar.add_route(
            method=HttpMethod.POST,
            path="webhook",
            handler=handler,
            metadata=metadata,
        )

        assert "/api/channels/test/webhook" in registrar.registered_paths

    def test_add_route_duplicate_path_raises(self, registrar):
        """Test that adding duplicate path raises ValueError."""

        async def handler(request):
            class Response:
                status_code = 200
                headers = {}
                body = b"ok"

            return Response()

        registrar.add_route(
            method=HttpMethod.POST,
            path="webhook",
            handler=handler,
        )

        with pytest.raises(ValueError, match="Route already registered"):
            registrar.add_route(
                method=HttpMethod.POST,
                path="webhook",
                handler=handler,
            )

    def test_add_route_invalid_path_raises(self, registrar):
        """Test that invalid path raises ValueError."""

        async def handler(request):
            class Response:
                status_code = 200
                headers = {}
                body = b"ok"

            return Response()

        with pytest.raises(ValueError, match="Invalid route path"):
            registrar.add_route(
                method=HttpMethod.POST,
                path="../admin",
                handler=handler,
            )

    def test_add_routes_batch(self, registrar):
        """Test adding multiple routes at once."""
        from app.channels.protocols.route_registrar import (
            RouteDefinition,
        )

        async def handler1(request):
            class Response:
                status_code = 200
                headers = {}
                body = b"ok"

            return Response()

        async def handler2(request):
            class Response:
                status_code = 200
                headers = {}
                body = b"ok"

            return Response()

        routes = [
            RouteDefinition(
                method=HttpMethod.POST,
                path="webhook",
                handler=handler1,
            ),
            RouteDefinition(
                method=HttpMethod.GET,
                path="status",
                handler=handler2,
            ),
        ]

        registrar.add_routes(routes)

        assert "/api/channels/test/webhook" in registrar.registered_paths
        assert "/api/channels/test/status" in registrar.registered_paths

    def test_security_policy_enforcement(self, app):
        """Test that security policy is enforced."""
        policy = RouteSecurityPolicy(
            enforce_prefix=True,
            blocked_paths=["/admin"],
        )

        registrar = FastAPIRouteRegistrar(
            app=app,
            channel_name="test",
            security_policy=policy,
        )

        async def handler(request):
            class Response:
                status_code = 200
                headers = {}
                body = b"ok"

            return Response()

        with pytest.raises(ValueError, match="Invalid route path"):
            registrar.add_route(
                method=HttpMethod.POST,
                path="admin",
                handler=handler,
            )

    def test_auth_dependency_injection(self, app):
        """Test that auth_dependency is properly injected."""
        from fastapi import Depends

        def get_user_id():
            return "user123"

        registrar = FastAPIRouteRegistrar(
            app=app,
            channel_name="test",
            auth_dependency=Depends(get_user_id),
        )

        assert registrar.auth_dependency is not None

    def test_multiple_http_methods(self, registrar):
        """Test registering different HTTP methods."""

        async def handler(request):
            class Response:
                status_code = 200
                headers = {}
                body = b"ok"

            return Response()

        registrar.add_route(
            method=HttpMethod.GET,
            path="status",
            handler=handler,
        )

        registrar.add_route(
            method=HttpMethod.POST,
            path="webhook",
            handler=handler,
        )

        registrar.add_route(
            method=HttpMethod.PUT,
            path="config",
            handler=handler,
        )

        assert len(registrar.registered_paths) == 3
