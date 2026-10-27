"""Channel execution preamble types and security config builder.

[INPUT]
- app.ai_agents.agents::GeneralAgentParams (POS: General agent runtime parameter bundle)
- app.ai_agents.general_agent.agent::GeneralAgent (POS: Business-layer general agent wrapper)
- app.channels.types::METADATA_APPROVAL_WINDOW_SECONDS_KEY, OutboundMessage, ProgressUpdate (POS: Channel outbound message envelope; per-turn approval wait key)
- app.core.channel_bridge.config_parsers::SessionPolicy (POS: Session policy parsing)
- app.core.types.business::ModelConfig (POS: Model configuration types)
- myrm_agent_harness.core.security.types::EphemeralUserCredential (POS: Ephemeral per-session credential carried by user_credentials_ctx)

[OUTPUT]
ChannelExecutionPrep, PrepareChannelExecutionResult, ChannelAgentBuildResult,
ChannelAgentBuildOutcome (XOR: result | early_reply), build_security_config() (user config + the turn's approval wait + YOLO state)

[POS]
preamble 子模块：preamble 阶段数据结构与安全配置组装。
"""

from __future__ import annotations

from contextvars import Token
from dataclasses import dataclass

from langgraph.types import Command
from myrm_agent_harness.core.security.types import EphemeralUserCredential

from app.ai_agents.agents import GeneralAgentParams
from app.ai_agents.general_agent.agent import GeneralAgent
from app.channels.types import METADATA_APPROVAL_WINDOW_SECONDS_KEY, OutboundMessage, ProgressUpdate
from app.core.channel_bridge.config_parsers import SessionPolicy
from app.core.channel_bridge.executor_helpers import ChannelChatHistory
from app.core.types.business import ModelConfig


def build_security_config(
    base_config: dict[str, object] | None,
    metadata: dict[str, object],
) -> dict[str, object]:
    """The security config of one channel turn: the user's config plus what the turn's message sets.

    A turn that carries ``METADATA_APPROVAL_WINDOW_SECONDS_KEY`` (a delegated run, whose requester is not watching the
    chat) waits that long for a tool approval instead of the configured window; the harness bounds the value.
    """
    config = dict(base_config) if base_config else {}
    window = metadata.get(METADATA_APPROVAL_WINDOW_SECONDS_KEY)
    if isinstance(window, (int, float)) and not isinstance(window, bool) and window > 0:
        config["approvalTimeoutSeconds"] = int(window)
    yolo_state = metadata.get("yolo_state")
    if yolo_state and isinstance(yolo_state, tuple) and len(yolo_state) == 2:
        enabled_at, timeout = yolo_state
        config["yolo_mode_enabled"] = True
        config["yolo_mode_enabled_at"] = enabled_at
        config["yolo_mode_timeout"] = timeout
    return config


@dataclass
class ChannelExecutionPrep:
    agent: GeneralAgent
    token_ctx: Token[tuple[EphemeralUserCredential, ...]]
    chat_id: str
    chat_history: ChannelChatHistory
    query_input: str | list[dict[str, object]] | Command[object]
    channel_budget_key: str | None
    memory_settings: dict[str, object]
    lite_model_cfg: ModelConfig | None
    session_was_auto_reset: bool
    session_policy: SessionPolicy
    params: GeneralAgentParams
    agent_engine_params: dict[str, object] | None
    user_timezone: str | None


@dataclass
class PrepareChannelExecutionResult:
    prep: ChannelExecutionPrep | None = None
    pre_events: tuple[ProgressUpdate | OutboundMessage, ...] = ()


@dataclass
class ChannelAgentBuildResult:
    agent: GeneralAgent
    token_ctx: Token[tuple[EphemeralUserCredential, ...]]
    query_input: str | list[dict[str, object]] | Command[object]
    params: GeneralAgentParams


@dataclass
class ChannelAgentBuildOutcome:
    result: ChannelAgentBuildResult | None = None
    early_reply: OutboundMessage | None = None
    pre_events: tuple[ProgressUpdate, ...] = ()

    def __post_init__(self) -> None:
        has_result = self.result is not None
        has_early = self.early_reply is not None
        if has_result == has_early:
            raise ValueError(
                "ChannelAgentBuildOutcome requires exactly one of result or early_reply",
            )
