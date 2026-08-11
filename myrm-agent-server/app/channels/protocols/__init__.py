"""Channel system protocols — interfaces for business-layer injection."""

from app.channels.protocols.adapters import RequestAdapter, ResponseAdapter
from app.channels.protocols.agent import AgentExecutor
from app.channels.protocols.async_login import (
    AsyncLoginProtocol,
    LoginEvent,
    LoginMethod,
    LoginState,
    LoginStatus,
)
from app.channels.protocols.compact import CompactHandler, CompactResult
from app.channels.protocols.inbound_profile import (
    CHANNEL_INBOUND_SPECS,
    ChannelInboundSpec,
    InboundMode,
    IngressTransport,
    resolve_channel_ingress_mode,
)
from app.channels.protocols.pairing import (
    ChannelPolicyProvider,
    DmPolicy,
    GroupPolicy,
    GroupTriggerMode,
    PairingStatus,
    PairingStore,
)
from app.channels.protocols.rate_limiter import (
    InMemoryRateLimiter,
    NoOpRateLimiter,
    RateLimiterProtocol,
)
from app.channels.protocols.route_registrar import (
    CORSConfig,
    GenericRequest,
    GenericResponse,
    HttpMethod,
    RouteDefinition,
    RouteMetadata,
    RouteRegistrar,
    RouteSecurityPolicy,
)
from app.channels.protocols.topic import TopicManager
from app.channels.protocols.turn_management import (
    RetryHandler,
    RetryResult,
    UndoHandler,
    UndoResult,
)

__all__ = [
    "AgentExecutor",
    "AsyncLoginProtocol",
    "CHANNEL_INBOUND_SPECS",
    "CORSConfig",
    "ChannelInboundSpec",
    "ChannelPolicyProvider",
    "CompactHandler",
    "CompactResult",
    "DmPolicy",
    "GenericRequest",
    "GenericResponse",
    "GroupPolicy",
    "GroupTriggerMode",
    "HttpMethod",
    "InMemoryRateLimiter",
    "InboundMode",
    "IngressTransport",
    "LoginEvent",
    "LoginMethod",
    "LoginState",
    "LoginStatus",
    "NoOpRateLimiter",
    "PairingStatus",
    "PairingStore",
    "RateLimiterProtocol",
    "RequestAdapter",
    "ResponseAdapter",
    "RetryHandler",
    "RetryResult",
    "RouteDefinition",
    "RouteMetadata",
    "RouteRegistrar",
    "RouteSecurityPolicy",
    "TopicManager",
    "UndoHandler",
    "UndoResult",
    "resolve_channel_ingress_mode",
]
