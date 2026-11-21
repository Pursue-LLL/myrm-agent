"""Shared types for agent stream session execution.

[INPUT]
- app.ai_agents::GeneralAgentParams (POS: Agent 参数定义层。纯参数数据结构，解耦 AgentFactory 创建逻辑与 Pydantic 参数校验)
- app.services.agent.params::AgentRequest (POS: Agent parameter conversion and model resolution)
- app.services.agent.stream_session.lazy_session_gate::PendingSessionDraft (POS: Stream-session persistence gate: no session row or sandbox directory exists until the first active generation event)
- app.services.agent.streaming_support.stream_collector::StreamContentCollector (POS: Agent API persistence helper. Converts transient SSE events into durable Message.extra_data metadata)
- app.services.copilot.run_digest_store::RunSession (POS: handle of the run digest the turn began, by which the turn ends only its own run)
- myrm_agent_harness.agent.streaming.stream_buffer::GlobalStreamRegistry (POS: Harness engine-layer SSE reconnect replay buffer)
- myrm_agent_harness.utils.runtime.cancellation::CancellationToken (POS: Cancellation token mechanism. Provides request-level cancellation state management with graceful async cancellation support.)
- myrm_agent_harness.utils.runtime.steering::SteeringToken (POS: Steering token mechanism. Allows external message injection during Agent runtime to interrupt the current tool chain)

[OUTPUT]
- AgentStreamSession: the state of one agent turn shared by chunk generation, disconnect watch, pump and finalize
- GRACE_PERIOD_SECONDS: how long a direct-SSE client may stay away before its turn is cancelled

[POS]
Single-turn session state of the stream pipeline: the one object the stream_session modules pass around.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Literal

from fastapi import Request
from myrm_agent_harness.agent.goals.protocols import GoalProvider
from myrm_agent_harness.agent.streaming.stream_buffer import GlobalStreamRegistry
from myrm_agent_harness.utils.runtime.cancellation import CancellationToken
from myrm_agent_harness.utils.runtime.steering import SteeringToken

from app.ai_agents import GeneralAgentParams
from app.services.agent.params import AgentRequest
from app.services.agent.stream_session.lazy_session_gate import PendingSessionDraft
from app.services.agent.streaming_support.stream_collector import StreamContentCollector
from app.services.copilot.run_digest_store import RunSession

GRACE_PERIOD_SECONDS = 180.0
ACTIVITY_STALE_SECONDS = 600.0


@dataclass
class AgentStreamSession:
    request: AgentRequest
    http_request: Request
    params: GeneralAgentParams
    cancel_token: CancellationToken
    steering_token: SteeringToken | None
    routing_tier: str | None
    archive_restore_results: list[dict[str, object]]
    registry: GlobalStreamRegistry
    collector: StreamContentCollector
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
    disconnect_monotonic: float | None = field(default=None)
    last_activity_monotonic: float = field(default_factory=time.monotonic)
    migration_live_readiness_status: Literal["ready", "warning", "critical"] | None = field(default=None)
    pending_session_draft: PendingSessionDraft | None = field(default=None)
    # The run digest the turn began, and the replay marker row it wrote: each lets the turn end only what is its own.
    digest_run: RunSession | None = field(default=None)
    turn_marker_id: str | None = field(default=None)
    # Set once finalize has run to its end; the safety net of the turn body acts only while a turn is not torn down.
    torn_down: bool = field(default=False)
