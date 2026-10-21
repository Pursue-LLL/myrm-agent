"""Service layer for Agent Session Multiplexing and cross-agent coordination.

[INPUT]
- myrm_agent_harness.agent.sub_agents.multiplexer::(
    AgentSessionMultiplexer, get_session_multiplexer, MultiplexerSessionState
  )
- pydantic::BaseModel, Field

[OUTPUT]
- AgentMultiplexerService: High-level multiplexer service for API endpoints.
- MultiplexerSessionSummaryDTO: Serialized session overview.
- MultiplexerInspectDTO: Read-only observational inspection payload.
- RegisterMultiplexerSessionRequest: Creation payload for a multiplexed session.
- InjectInstructionRequest: Steering payload to inject into an agent.
- InjectInstructionResponse: Confirmation of instruction enqueueing.

[POS]
Server-side service orchestrating tmux-style persistent multi-agent sessions.
"""

from __future__ import annotations

from typing import cast

from myrm_agent_harness.agent.sub_agents.multiplexer import (
    AgentSessionMultiplexer,
    MultiplexerSessionState,
    get_session_multiplexer,
)
from pydantic import BaseModel, Field


class MultiplexerSessionSummaryDTO(BaseModel):
    """Summarized descriptor of a multiplexed agent session."""

    session_id: str
    parent_session_id: str | None = None
    agent_type: str
    task_objective: str
    state: str
    is_headless: bool
    started_at: float
    updated_at: float
    artifacts_count: int
    metadata: dict[str, object] = Field(default_factory=dict)


class MultiplexerInspectDTO(BaseModel):
    """Observational snapshot of session status, logs, and artifacts."""

    session_id: str
    agent_type: str
    state: str
    is_headless: bool
    task_objective: str
    log_tail: list[str]
    artifacts: list[str]
    pending_instructions_count: int
    snapshot_timestamp: float


class RegisterMultiplexerSessionRequest(BaseModel):
    """Request payload to register or attach a multiplexed session."""

    session_id: str
    agent_type: str
    task_objective: str
    parent_session_id: str | None = None
    is_headless: bool = False
    metadata: dict[str, object] = Field(default_factory=dict)


class InjectInstructionRequest(BaseModel):
    """Request payload to inject a steering instruction into a session."""

    instruction: str
    source_agent: str = "orchestrator"


class InjectInstructionResponse(BaseModel):
    """Response payload acknowledging injected instruction."""

    success: bool
    session_id: str
    instruction_id: str
    message: str
    queued_instructions_count: int


class AgentMultiplexerService:
    """Business service managing persistent agent sessions and inspect/instruct dispatch."""

    def __init__(self, multiplexer: AgentSessionMultiplexer | None = None) -> None:
        self._mux = multiplexer or get_session_multiplexer()

    def list_sessions(
        self,
        *,
        parent_session_id: str | None = None,
        state: str | None = None,
        is_headless: bool | None = None,
    ) -> list[MultiplexerSessionSummaryDTO]:
        """List active sessions matching optional filters."""
        typed_state = cast(MultiplexerSessionState, state) if state else None
        sessions = self._mux.list_sessions(
            parent_session_id=parent_session_id,
            state=typed_state,
            is_headless=is_headless,
        )

        return [
            MultiplexerSessionSummaryDTO(
                session_id=s.session_id,
                parent_session_id=s.parent_session_id,
                agent_type=s.agent_type,
                task_objective=s.task_objective,
                state=s.state,
                is_headless=s.is_headless,
                started_at=s.started_at,
                updated_at=s.updated_at,
                artifacts_count=len(s.artifacts),
                metadata=s.metadata,
            )
            for s in sessions
        ]

    def register_session(
        self,
        req: RegisterMultiplexerSessionRequest,
    ) -> MultiplexerSessionSummaryDTO:
        """Register a new persistent session in the multiplexer."""
        s = self._mux.register_session(
            session_id=req.session_id,
            agent_type=req.agent_type,
            task_objective=req.task_objective,
            parent_session_id=req.parent_session_id,
            is_headless=req.is_headless,
            metadata=req.metadata,
        )
        return MultiplexerSessionSummaryDTO(
            session_id=s.session_id,
            parent_session_id=s.parent_session_id,
            agent_type=s.agent_type,
            task_objective=s.task_objective,
            state=s.state,
            is_headless=s.is_headless,
            started_at=s.started_at,
            updated_at=s.updated_at,
            artifacts_count=len(s.artifacts),
            metadata=s.metadata,
        )

    def inspect_session(
        self,
        session_id: str,
        tail_lines: int = 50,
    ) -> MultiplexerInspectDTO | None:
        """Inspect progress and logs of an active session."""
        snapshot = self._mux.inspect_session(session_id, tail_lines=tail_lines)
        if not snapshot:
            return None

        return MultiplexerInspectDTO(
            session_id=snapshot.session_id,
            agent_type=snapshot.agent_type,
            state=snapshot.state,
            is_headless=snapshot.is_headless,
            task_objective=snapshot.task_objective,
            log_tail=snapshot.log_tail,
            artifacts=snapshot.artifacts,
            pending_instructions_count=snapshot.pending_instructions_count,
            snapshot_timestamp=snapshot.snapshot_timestamp,
        )

    def instruct_session(
        self,
        session_id: str,
        req: InjectInstructionRequest,
    ) -> InjectInstructionResponse:
        """Inject guidance or corrections into a session."""
        res = self._mux.inject_instruction(
            session_id,
            req.instruction,
            source_agent=req.source_agent,
        )
        return InjectInstructionResponse(
            success=res.success,
            session_id=res.session_id,
            instruction_id=res.instruction_id,
            message=res.message,
            queued_instructions_count=res.queued_instructions_count,
        )
