"""Channel execution preamble: config, session, and agent assembly for a channel turn."""

from .agent import build_channel_execution_agent
from .backfill import maybe_backfill_channel_history
from .instructions import enrich_channel_user_instructions
from .preamble import prepare_channel_execution
from .session import ChannelSessionContext, resolve_channel_session_context
from .types import (
    ChannelAgentBuildOutcome,
    ChannelAgentBuildResult,
    ChannelExecutionPrep,
    PrepareChannelExecutionResult,
    build_security_config,
)

__all__ = [
    "ChannelAgentBuildOutcome",
    "ChannelAgentBuildResult",
    "ChannelExecutionPrep",
    "ChannelSessionContext",
    "PrepareChannelExecutionResult",
    "build_channel_execution_agent",
    "build_security_config",
    "enrich_channel_user_instructions",
    "maybe_backfill_channel_history",
    "prepare_channel_execution",
    "resolve_channel_session_context",
]
