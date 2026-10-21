"""Channel execution preamble package exports.

[INPUT]
- execute_preamble.agent (POS: build channel execution agent)
- execute_preamble.backfill (POS: channel history backfill)
- execute_preamble.instructions (POS: user instruction enrichment)
- execute_preamble.preamble (POS: prepare channel execution)
- execute_preamble.session (POS: channel session context)
- execute_preamble.types (POS: preamble DTOs and security config)

[OUTPUT]
- Re-exports for channel turn preamble assembly

[POS]
Public surface for channel executor preamble: session, agent build, and prep helpers.
"""

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
