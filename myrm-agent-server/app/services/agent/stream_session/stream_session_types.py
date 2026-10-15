"""Shared types for agent stream session execution.

[INPUT]
- app.ai_agents::GeneralAgentParams (POS: Agent 参数定义层。纯参数数据结构，解耦 AgentFactory 创建逻辑与 Pydantic 参数校验)
- app.core.types::ModelConfig (POS: Business-specific type definitions used across the business layer)
- app.services.agent.params::AgentRequest (POS: Agent parameter conversion and model resolution)
- app.services.agent.stream_session.lazy_session_gate::PendingSessionDraft (POS: Stream-session persistence gate: no session row or sandbox directory exists until the first active generation event)
- app.services.agent.streaming_support.stream_collector::StreamContentCollector (POS: Agent API persistence helper. Converts transient SSE events into durable Message.extra_data metadata)
- app.services.chat.compact_service::CompactResult (POS: Chat context compaction facade)
- myrm_agent_harness.agent.streaming.stream_buffer::GlobalStreamRegistry (POS: Harness engine-layer SSE reconnect replay buffer)
- myrm_agent_harness.utils.runtime.cancellation::CancellationToken (POS: Cancellation token mechanism. Provides request-level cancellation state management)
- myrm_agent_harness.utils.runtime.steering::SteeringToken (POS: Steering token mechanism. Allows external message injection during Agent runtime to interrupt the current tool chain)

[OUTPUT]
- AgentStreamSession: the state of one agent turn shared by chunk generation, disconnect watch, pump and finalize
- GRACE_PERIOD_SECONDS: how long a direct-SSE client may stay away before its turn is cancelled

[POS]
Single-turn session state of the stream pipeline: the one object the stream_session modules pass around.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from fastapi import Request
from myrm_agent_harness.agent.goals.protocols import GoalProvider
from myrm_agent_harness.agent.streaming.stream_buffer import GlobalStreamRegistry
from myrm_agent_harness.utils.runtime.cancellation import CancellationToken
from myrm_agent_harness.utils.runtime.steering import SteeringToken

from app.ai_agents import GeneralAgentParams
from app.core.types import ModelConfig
from app.services.agent.params import AgentRequest
from app.services.agent.stream_session.lazy_session_gate import PendingSessionDraft
from app.services.agent.streaming_support.stream_collector import StreamContentCollector
from app.services.chat.compact_service import CompactResult

GRACE_PERIOD_SECONDS = 180.0


@dataclass
class AgentStreamSession:
    request: AgentRequest
    http_request: Request
    params: GeneralAgentParams
    cancel_token: CancellationToken
    steering_token: SteeringToken | None
    routing_tier: str | None
    archive_restore_results: list[dict[str, object]]
    research_model_cfg: ModelConfig | None
    registry: GlobalStreamRegistry
    collector: StreamContentCollector
    is_long_running_task: bool
    goal_provider: GoalProvider | None
    extra_context: dict[str, object]
    routing_specialty: str | None = field(default=None)
    routing_reason: str | None = field(default=None)
    context_warnings: list[str] = field(default_factory=list)
    stream_started_at_monotonic: float = field(default=0.0)
    stream_ttft_ms: int | None = field(default=None)
    had_fatal_error: bool = field(default=False)
    turn_capability_terminal_recorded: bool = field(default=False)
    disconnect_time: float | None = field(default=None)
    migration_live_readiness_status: Literal["ready", "warning", "critical"] | None = field(default=None)
    pre_reply_compact_result: CompactResult | None = field(default=None)
    pre_reply_compact_sse_sent: bool = field(default=False)
    pending_session_draft: PendingSessionDraft | None = field(default=None)
