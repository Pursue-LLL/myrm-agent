"""Shared types for agent stream session execution."""

from __future__ import annotations

from dataclasses import dataclass, field

from fastapi import Request
from myrm_agent_harness.utils.runtime.cancellation import CancellationMonitor, CancellationToken
from myrm_agent_harness.utils.runtime.steering import SteeringToken

from app.ai_agents import GeneralAgentParams
from app.core.types import ModelConfig
from app.services.agent.params import AgentRequest
from app.services.agent.streaming_support.stream_collector import StreamContentCollector

GRACE_PERIOD_SECONDS = 180.0


@dataclass
class AgentStreamSession:
    request: AgentRequest
    http_request: Request
    params: GeneralAgentParams
    cancel_token: CancellationToken
    steering_token: SteeringToken | None
    routing_tier: str | None
    context_warnings: list[str]
    archive_restore_results: list[object]
    research_model_cfg: ModelConfig | None
    registry: object
    collector: StreamContentCollector
    monitor: CancellationMonitor
    is_long_running_task: bool
    goal_provider: object | None
    extra_context: dict[str, object]
    consensus_config: dict[str, object] | None = field(default=None)
    consensus_ref_model_cfgs: list[object] | None = field(default=None)
    consensus_agg_model_cfg: object | None = field(default=None)
    durable_registered: bool = field(default=False)
    had_fatal_error: bool = field(default=False)
    disconnect_time: float | None = field(default=None)
    entitlement_preflight_text: str | None = field(default=None)
