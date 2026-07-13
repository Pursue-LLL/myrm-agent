"""Channel execution preamble types and security config builder.

[INPUT]
app.channels.types::InboundMessage (POS: Channel inbound message envelope)

[OUTPUT]
ChannelExecutionPrep, PrepareChannelExecutionResult, build_security_config()

[POS]
execute_preamble 子模块：preamble 阶段数据结构与安全配置组装。
"""

from __future__ import annotations

from dataclasses import dataclass

from langgraph.types import Command

from app.ai_agents.agents import GeneralAgentParams
from app.ai_agents.general_agent.agent import GeneralAgent
from app.channels.types import OutboundMessage, ProgressUpdate
from app.core.channel_bridge.config_parsers import SessionPolicy
from app.core.types.business import ModelConfig


def build_security_config(
    base_config: dict[str, object] | None,
    metadata: dict[str, object],
) -> dict[str, object]:
    config = dict(base_config) if base_config else {}
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
    token_ctx: object
    chat_id: str
    chat_history: list[object]
    query_input: str | Command[object]
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
