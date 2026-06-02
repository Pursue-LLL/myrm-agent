"""Channel route registry for automatic route discovery and registration.

Collects routes from all channels and registers them with FastAPI,
managing lifecycle, observability, and health reporting.

[INPUT]
- fastapi::FastAPI (POS: Out-of-the-box FastAPI implementation. Users can directly use these classes without implementing RouteRegistrar Protocol themselves.)
- app.channels.core.gateway::ChannelGateway (POS: Channel system entry point. Manages all channel lifecycles, health checks, and error isolation. Supports outbound-only mode (push only) and bidirectional mode (push + receive + agent processing).)
- app.channels.protocols.route_registrar::RouteSecurityPolicy (POS: Protocol layer for dynamic HTTP route registration. Enables channels to declare their own HTTP endpoints while maintaining framework independence. Business layer implements RouteRegistrar for a specific web framework (e.g. FastAPI via ``myrm-agent-harness[fastapi]``).)
- app.channels.protocols.rate_limiter::RateLimiterProtocol, (POS: Per-User Rate Limiter for Skill Optimization)
- app.channels.implementations.fastapi.registrar::FastAPIRouteRegistrar (POS: Framework-layer implementation of route registration for FastAPI. Enforces security policies, applies middleware, and manages route lifecycle. Business layer injects authentication dependency via auth_dependency parameter.)

[OUTPUT]
- ChannelRouteRegistry: Manages channel route registration lifecycle

[POS]
Orchestration layer for channel route registration. Discovers channels
from Gateway, creates registrars, and manages registration lifecycle.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI

from app.channels.core.gateway import ChannelGateway
from app.channels.implementations.fastapi.registrar import (
    FastAPIRouteRegistrar,
)
from app.channels.protocols.rate_limiter import (
    NoOpRateLimiter,
    RateLimiterProtocol,
)
from app.channels.protocols.route_registrar import (
    RouteSecurityPolicy,
)

logger = logging.getLogger(__name__)


class ChannelRouteRegistry:
    """Manages automatic route registration from all channels.

    Discovers channels from ChannelGateway and registers their custom
    HTTP routes (webhooks, login pages, status endpoints).

    Example:
        from app.channels.implementations.fastapi import ChannelRouteRegistry
        from fastapi import Depends

        registry = ChannelRouteRegistry(
            gateway,
            auth_dependency=Depends(get_user_id),
        )
        registry.register_all(app)
    """

    def __init__(
        self,
        gateway: ChannelGateway,
        security_policy: RouteSecurityPolicy | None = None,
        rate_limiter: RateLimiterProtocol | None = None,
        auth_dependency: object | None = None,
    ) -> None:
        """Initialize channel route registry.

        Args:
            gateway: ChannelGateway instance containing all channels
            security_policy: Optional security policy for path validation
            rate_limiter: Optional rate limiting implementation (defaults to NoOpRateLimiter)
            auth_dependency: Optional FastAPI dependency for authentication
                (e.g., Depends(get_current_user_id))
        """
        self.gateway = gateway
        self.security_policy = security_policy or self._default_security_policy()
        self.rate_limiter = rate_limiter or NoOpRateLimiter()
        self.auth_dependency = auth_dependency
        self.registered_channels: dict[str, int] = {}
        self.total_routes_count = 0

    @staticmethod
    def _default_security_policy() -> RouteSecurityPolicy:
        """Create default security policy.

        Returns:
            RouteSecurityPolicy with sensible defaults
        """
        return RouteSecurityPolicy(
            enforce_prefix=True,
            blocked_paths=[
                "/admin",
                "/api/users",
                "/api/config",
                "/api/auth",
                "/api/database",
            ],
        )

    def register_all(self, app: FastAPI) -> None:
        """Discover and register routes from all channels.

        Iterates through all channels in the gateway, creates registrars
        for each, and calls their register_routes() methods.

        Args:
            app: FastAPI application instance
        """
        logger.info("Starting channel route registration")

        for channel_name, channel in self.gateway.bus._channels.items():
            if not hasattr(channel, "register_routes"):
                logger.debug(
                    "Channel has no register_routes method",
                    extra={"channel": channel_name},
                )
                continue

            try:
                registrar = FastAPIRouteRegistrar(
                    app=app,
                    channel_name=channel_name,
                    security_policy=self.security_policy,
                    apply_middleware=True,
                    rate_limiter=self.rate_limiter,
                    auth_dependency=self.auth_dependency,
                )

                channel.register_routes(registrar)

                route_count = len(registrar.registered_paths)
                self.registered_channels[channel_name] = route_count
                self.total_routes_count += route_count

                logger.info(
                    "Registered channel routes",
                    extra={
                        "channel": channel_name,
                        "route_count": route_count,
                        "paths": list(registrar.registered_paths),
                    },
                )

            except Exception as e:
                logger.error(
                    "Failed to register channel routes",
                    extra={
                        "channel": channel_name,
                        "error": str(e),
                    },
                    exc_info=True,
                )

        logger.info(
            "Channel route registration complete",
            extra={
                "total_channels": len(self.gateway.bus._channels),
                "registered_channels": len(self.registered_channels),
                "total_routes": self.total_routes_count,
            },
        )

    def get_health_report(self) -> dict[str, object]:
        """Get health report of all registered routes.

        Returns:
            Dictionary with health information
        """
        return {
            "total_channels": len(self.gateway.bus._channels),
            "channels_with_routes": list(self.registered_channels.keys()),
            "registered_channels_count": len(self.registered_channels),
            "total_routes": self.total_routes_count,
            "routes_by_channel": self.registered_channels,
            "security_policy": {
                "enforce_prefix": self.security_policy.enforce_prefix,
                "blocked_paths": self.security_policy.blocked_paths,
                "allowed_paths": self.security_policy.allowed_paths,
            },
        }

    def get_channels_with_routes(self) -> list[str]:
        """Get list of channel names that registered routes.

        Returns:
            List of channel names
        """
        return list(self.registered_channels.keys())

    def get_route_count(self, channel_name: str) -> int | None:
        """Get route count for a specific channel.

        Args:
            channel_name: Name of the channel

        Returns:
            Route count if channel registered routes, None otherwise
        """
        return self.registered_channels.get(channel_name)
