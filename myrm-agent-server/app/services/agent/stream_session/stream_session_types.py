"""Shared types for agent stream session execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from fastapi import Request
from myrm_agent_harness.utils.runtime.cancellation import (
    CancellationMonitor,
    CancellationToken,
)
from myrm_agent_harness.utils.runtime.steering import SteeringToken

from app.ai_agents import GeneralAgentParams
from app.core.types import ModelConfig
from app.services.agent.params import AgentRequest
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
    archive_restore_results: list[object]
    research_model_cfg: ModelConfig | None
    registry: object
    collector: StreamContentCollector
    monitor: CancellationMonitor
    is_long_running_task: bool
    goal_provider: object | None
    extra_context: dict[str, object]
    routing_specialty: str | None = field(default=None)
    routing_reason: str | None = field(default=None)
    context_warnings: list[str] = field(default_factory=list)
    stream_started_at_monotonic: float = field(default=0.0)
    stream_ttft_ms: int | None = field(default=None)
    durable_registered: bool = field(default=False)
    had_fatal_error: bool = field(default=False)
    turn_capability_terminal_recorded: bool = field(default=False)
    disconnect_time: float | None = field(default=None)
    entitlement_preflight_text: str | None = field(default=None)
    migration_live_readiness_status: Literal["ready", "warning", "critical"] | None = field(default=None)
    pre_reply_compact_result: CompactResult | None = field(default=None)
    pre_reply_compact_sse_sent: bool = field(default=False)
