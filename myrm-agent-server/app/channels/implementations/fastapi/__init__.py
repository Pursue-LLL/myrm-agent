"""FastAPI implementation of channel route registration system.

Provides ready-to-use implementations for FastAPI applications.

Installation:
    pip install myrm-agent-harness[fastapi]

Usage:
    from app.channels.implementations.fastapi import (
        FastAPIRouteRegistrar,
        FastAPIRequestAdapter,
        FastAPIResponseAdapter,
        ChannelRouteRegistry,
    )

    # Register channel routes
    registry = ChannelRouteRegistry(channel_gateway)
    registry.register_all(app)

[INPUT]
- fastapi::FastAPI, (POS: Out-of-the-box FastAPI implementation. Users can directly use these classes without implementing RouteRegistrar Protocol themselves.)
- channels.protocols::RouteRegistrar, (POS: Protocols for Skill Optimization Subsystem)

[OUTPUT]
- FastAPIRouteRegistrar: FastAPI-specific route registrar
- FastAPIRequestAdapter: Adapts FastAPI Request to GenericRequest
- FastAPIResponseAdapter: Adapts GenericResponse to FastAPI Response
- ChannelRouteRegistry: Orchestrates channel route registration

[POS]
Out-of-the-box FastAPI implementation. Users can directly use these
classes without implementing RouteRegistrar Protocol themselves.
"""

from app.channels.implementations.fastapi.adapters import (
    FastAPIRequestAdapter,
    FastAPIResponseAdapter,
)
from app.channels.implementations.fastapi.registrar import (
    FastAPIRouteRegistrar,
)
from app.channels.implementations.fastapi.registry import (
    ChannelRouteRegistry,
)

__all__ = [
    "ChannelRouteRegistry",
    "FastAPIRequestAdapter",
    "FastAPIResponseAdapter",
    "FastAPIRouteRegistrar",
]
