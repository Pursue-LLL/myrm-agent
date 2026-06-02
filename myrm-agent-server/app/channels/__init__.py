"""Multi-platform messaging channel toolkit.

Protocol-first design: the framework defines channel abstractions,
message types, routing logic, protocols, and storage. Concrete storage backends
and agent executors are provided by the application layer via dependency
injection.

Provides:
- BaseChannel: abstract interface for all channel providers
- MessageBus: async message routing (outbound dispatch + inbound collection)
- ChannelGateway: lifecycle management, health checks, error isolation
- AgentRouter: inbound message → identity resolution → Agent execution → reply
- Protocols: PairingStore (user binding), AgentExecutor (agent invocation)
- Storage: LoginSessionStore (async login), CredentialsStore (encrypted)
- Providers: WebhookChannel, TelegramChannel (framework-level)


[INPUT]
- core.base::BaseChannel, InboundHandler (POS: channel abstract base class)
- core.bus::MessageBus (POS: async message bus)
- core.gateway::ChannelGateway (POS: channel lifecycle gateway)
- protocols (POS: channel protocol definitions)
- routing.router::AgentRouter (POS: inbound message routing hub)
- storage (POS: channel credential and session storage)
- types (POS: channel message and status types)

[OUTPUT]
- BaseChannel, InboundHandler, MessageBus, ChannelGateway, AgentRouter: core channel components
- AgentExecutor, ChannelPolicyProvider, DmPolicy, GroupPolicy, PairingStore, TopicManager: protocols
- CredentialsStore, InMemorySessionStore, LoginSessionData, LoginSessionStoreProtocol: storage
- ChannelCapabilities, ChannelStatus, CronContext, InboundMessage, etc.: message and status types

[POS]
Channels toolkit entry point. Aggregates channel abstractions, message bus, gateway,
routing, protocols, storage, and type definitions for multi-platform messaging.
"""

from app.channels.core.base import BaseChannel, InboundHandler
from app.channels.core.bus import MessageBus
from app.channels.core.gateway import ChannelGateway
from app.channels.protocols import (
    AgentExecutor,
    ChannelPolicyProvider,
    DmPolicy,
    GroupPolicy,
    PairingStore,
    TopicManager,
)
from app.channels.routing.router import AgentRouter
from app.channels.storage import (
    CredentialsStore,
    InMemorySessionStore,
    LoginSessionData,
    LoginSessionStoreProtocol,
)
from app.channels.types import (
    ChannelCapabilities,
    ChannelStatus,
    CronContext,
    InboundMessage,
    OutboundMessage,
    SessionKey,
    SessionPolicy,
    SessionResetMode,
    TopicContext,
    compute_daily_epoch,
    extract_cron_context,
)

__all__ = [
    "AgentExecutor",
    "AgentRouter",
    "BaseChannel",
    "ChannelCapabilities",
    "ChannelGateway",
    "ChannelPolicyProvider",
    "ChannelStatus",
    "CredentialsStore",
    "CronContext",
    "DmPolicy",
    "GroupPolicy",
    "InMemorySessionStore",
    "InboundHandler",
    "InboundMessage",
    "LoginSessionData",
    "LoginSessionStoreProtocol",
    "MessageBus",
    "OutboundMessage",
    "PairingStore",
    "SessionKey",
    "SessionPolicy",
    "SessionResetMode",
    "TopicContext",
    "TopicManager",
    "compute_daily_epoch",
    "extract_cron_context",
]
