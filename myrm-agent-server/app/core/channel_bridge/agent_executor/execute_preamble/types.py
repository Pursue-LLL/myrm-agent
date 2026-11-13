"""Channel execution preamble types and the security overlay of a channel turn.

[INPUT]
- app.ai_agents.agents::GeneralAgentParams (POS: General agent runtime parameter bundle)
- app.ai_agents.general_agent.agent::GeneralAgent (POS: Business-layer general agent wrapper)
- app.channels.types::METADATA_APPROVAL_WINDOW_SECONDS_KEY, OutboundMessage, ProgressUpdate, SessionPolicy (POS: Channel outbound message envelope; per-turn approval wait key; declarative session reset policy)
- app.core.channel_bridge.learn_handler::learn_authoring_prompt_text (POS: /learn authoring turn detection)
- app.core.security.session_overlay::SecurityOverlaySpec, YoloGrant (POS: request-scoped security overlays)
- app.core.types.business::ModelConfig (POS: Model configuration types)
- myrm_agent_harness.core.security.types::EphemeralUserCredential (POS: Ephemeral per-session credential carried by user_credentials_ctx)

[OUTPUT]
ChannelExecutionPrep, PrepareChannelExecutionResult, ChannelAgentBuildResult,
ChannelAgentBuildOutcome (XOR: result | early_reply), build_security_overlay() (the turn's approval wait, session YOLO state and /learn authoring as one overlay)

[POS]
preamble 子模块：preamble 阶段数据结构与本回合安全 overlay 组装。
"""

from __future__ import annotations

from collections.abc import Mapping
from contextvars import Token
from dataclasses import dataclass
from typing import TypeGuard

from langgraph.types import Command
from myrm_agent_harness.core.security.types import EphemeralUserCredential

from app.ai_agents.agents import GeneralAgentParams
from app.ai_agents.general_agent.agent import GeneralAgent
from app.channels.types import METADATA_APPROVAL_WINDOW_SECONDS_KEY, OutboundMessage, ProgressUpdate, SessionPolicy
from app.core.channel_bridge.executor_helpers import ChannelChatHistory
from app.core.channel_bridge.learn_handler import learn_authoring_prompt_text
from app.core.security.session_overlay import SecurityOverlaySpec, YoloGrant
from app.core.types.business import ModelConfig


def _is_number(value: object) -> TypeGuard[int | float]:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _whole_seconds(value: object) -> int | None:
    """*value* as whole seconds, at least one, when it is a positive number."""
    return max(1, int(value)) if _is_number(value) and value > 0 else None


def _yolo_grant(state: object) -> YoloGrant | None:
    """The grant of the router's ``(enabled_at, timeout)`` session state; ``None`` for any other shape."""
    if not (isinstance(state, tuple) and len(state) == 2):
        return None
    enabled_at, timeout = state
    if not _is_number(enabled_at):
        return None
    if timeout is None:
        return YoloGrant(enabled_at=enabled_at)
    seconds = _whole_seconds(timeout)
    return None if seconds is None else YoloGrant(enabled_at=enabled_at, timeout_seconds=seconds)


def build_security_overlay(metadata: Mapping[str, object], query: object) -> SecurityOverlaySpec:
    """The security overlay of one channel turn: what the turn's message and query set over the user's saved config.

    A turn that carries ``METADATA_APPROVAL_WINDOW_SECONDS_KEY`` (a delegated run, whose requester is not watching the
    chat) waits that long for a tool approval instead of the configured window; the harness bounds the value. The
    session YOLO state the router put on the message becomes a YOLO grant, and a ``/learn`` authoring query elevates
    ``skill_manage``. The agent keeps the overlay so every per-turn reload of the saved config layers it back.
    """
    return SecurityOverlaySpec(
        approval_window_seconds=_whole_seconds(metadata.get(METADATA_APPROVAL_WINDOW_SECONDS_KEY)),
        yolo=_yolo_grant(metadata.get("yolo_state")),
        learn_authoring=learn_authoring_prompt_text(query) is not None,
    )


@dataclass
class ChannelExecutionPrep:
    agent: GeneralAgent
    token_ctx: Token[tuple[EphemeralUserCredential, ...]]
    chat_id: str
    session_key: str
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
