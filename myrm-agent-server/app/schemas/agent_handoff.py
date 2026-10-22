"""
[POS] app/schemas/agent_handoff.py
[INPUT] pydantic
[OUTPUT] FailedApproachDTO, ImplicitConstraintDTO, AgentHandoffSpecDTO, FinalizeSessionRequestDTO, FinalizeSessionResponseDTO, ClaimHandoffRequestDTO, HandoffClaimReceiptDTO, CompleteHandoffRequestDTO, CancelHandoffRequestDTO, HandoffListResponseDTO, InChatAgentParticipantDTO, HandoffStageInfoDTO, InChatHandoffCardDTO, CreateInChatHandoffRequestDTO, HandoffActionRequestDTO, HandoffAdvanceStageRequestDTO

Pydantic schemas for typed cross-agent handoff protocol, CAS claim, and session finalization.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import time

from pydantic import BaseModel, ConfigDict, Field


class FailedApproachDTO(BaseModel):
    """Discarded hypothesis or route with concrete rationale and evidence."""

    model_config = ConfigDict(extra="forbid")

    approach_name: str = Field(..., min_length=1, description="Summary of the discarded solution route")
    rejected_reason: str = Field(..., min_length=1, description="Concrete rationale for discarding this approach")
    evidence_snippet: str = Field(default="", description="Verbatim error message, test log, or benchmark snippet")
    attempted_by_profile_id: str | None = Field(default=None, description="Agent profile that attempted the route")


class ImplicitConstraintDTO(BaseModel):
    """Discovered environmental, architectural, or latent business invariant."""

    model_config = ConfigDict(extra="forbid")

    scope: str = Field(..., min_length=1, description="Subsystem scope (e.g. database, sandbox, frontend)")
    constraint_rule: str = Field(..., min_length=1, description="The immutable invariant or rule statement")
    rationale: str = Field(default="", description="Contextual reasoning for this constraint")


class AgentHandoffSpecDTO(BaseModel):
    """Full snapshot of an agent handoff memorandum."""

    model_config = ConfigDict(extra="forbid")

    handoff_id: str = Field(..., description="Unique identifier for the handoff protocol packet")
    session_id: str = Field(..., description="Source conversation session identifier")
    source_profile_id: str = Field(..., description="Departing agent profile identifier")
    target_profile_id: str | None = Field(default=None, description="Designated recipient agent profile, or None")
    active_goal: str = Field(..., description="Primary mission and currently active milestone")
    failed_approaches: list[FailedApproachDTO] = Field(default_factory=list, description="Discarded implementation avenues")
    implicit_constraints: list[ImplicitConstraintDTO] = Field(default_factory=list, description="Latent business or runtime restrictions")
    errors_and_fixes: list[str] = Field(default_factory=list, description="Discovered pitfalls and fixes")
    pending_asks: list[str] = Field(default_factory=list, description="Unresolved questions or blockers")
    next_actions: list[str] = Field(default_factory=list, description="Sequential immediate action steps")
    status: str = Field(..., description="Current lifecycle state: pending, claimed, completed, cancelled")
    created_at: float = Field(..., description="Epoch creation timestamp")
    claimed_at: float | None = Field(default=None, description="Epoch timestamp when claimed by successor")
    claimed_by_profile_id: str | None = Field(default=None, description="Profile ID of the claiming successor agent")
    claimed_by_session_id: str | None = Field(default=None, description="Session ID where handoff was activated")
    completed_at: float | None = Field(default=None, description="Epoch timestamp when successor marked work complete")


class FinalizeSessionRequestDTO(BaseModel):
    """Request payload to finalize active session and write durable handoff memorandum."""

    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(..., min_length=1, description="Source session identifier")
    source_profile_id: str = Field(..., min_length=1, description="Current executing agent profile")
    target_profile_id: str | None = Field(default=None, description="Optional designated successor agent profile")
    active_goal: str = Field(..., min_length=1, description="Active working goal summary")
    failed_approaches: list[FailedApproachDTO] = Field(default_factory=list, description="Discarded approaches")
    implicit_constraints: list[ImplicitConstraintDTO] = Field(default_factory=list, description="Discovered constraints")
    errors_and_fixes: list[str] = Field(default_factory=list, description="Known errors and remedies")
    pending_asks: list[str] = Field(default_factory=list, description="Blockers or pending questions")
    next_actions: list[str] = Field(default_factory=list, description="Next actionable steps")


class FinalizeSessionResponseDTO(BaseModel):
    """Response acknowledging durable session finalization."""

    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(..., description="Finalized session ID")
    handoff_id: str = Field(..., description="Generated durable handoff ID")
    persisted_path: str = Field(..., description="Filesystem storage location of finalized handoff")
    status: str = Field(..., description="Initial state of the handoff packet")
    timestamp: float = Field(default_factory=time.time, description="Finalization epoch timestamp")


class ClaimHandoffRequestDTO(BaseModel):
    """Request payload to atomically claim an open handoff memorandum."""

    model_config = ConfigDict(extra="forbid")

    claimer_profile_id: str = Field(..., min_length=1, description="Successor agent profile attempting claim")
    claimer_session_id: str = Field(..., min_length=1, description="Successor conversation session acquiring ownership")


class HandoffClaimReceiptDTO(BaseModel):
    """Cryptographic-style receipt proving successful exactly-once claim."""

    model_config = ConfigDict(extra="forbid")

    handoff_id: str = Field(..., description="ID of the claimed handoff")
    claimed_by_profile_id: str = Field(..., description="Successor agent profile that acquired ownership")
    claimed_by_session_id: str = Field(..., description="Successor session that loaded the context")
    claim_timestamp: float = Field(..., description="Epoch timestamp of atomic transition")
    handoff_spec: AgentHandoffSpecDTO = Field(..., description="Full handoff snapshot acquired by recipient")


class CompleteHandoffRequestDTO(BaseModel):
    """Request payload to mark a claimed handoff as completed."""

    model_config = ConfigDict(extra="forbid")

    completing_session_id: str = Field(..., min_length=1, description="Session ID performing completion")


class CancelHandoffRequestDTO(BaseModel):
    """Request payload to cancel an active handoff."""

    model_config = ConfigDict(extra="forbid")

    cancelling_session_id: str = Field(..., min_length=1, description="Session ID issuing cancellation")
    reason: str = Field(..., min_length=1, description="Concrete cancellation reason")


class HandoffListResponseDTO(BaseModel):
    """Response containing a collection of handoff memoranda."""

    model_config = ConfigDict(extra="forbid")

    handoffs: list[AgentHandoffSpecDTO] = Field(default_factory=list, description="Collection of handoff specs")
    total_count: int = Field(ge=0, description="Total matching handoff records")


class InChatAgentParticipantDTO(BaseModel):
    """Participant metadata for in-chat task delegation."""

    model_config = ConfigDict(extra="forbid")

    profile_id: str = Field(..., min_length=1, description="Agent profile identifier")
    name: str = Field(..., min_length=1, description="Display name of the agent")
    avatar: str = Field(default="", description="Avatar image URL or icon identifier")
    role: str = Field(..., min_length=1, description="Functional role or specialty")
    personality_tags: list[str] = Field(default_factory=list, description="Personality traits or behavioral tags")


class HandoffStageInfoDTO(BaseModel):
    """Single stage in the BkashJosi Five-Stage Orchestration Stack."""

    model_config = ConfigDict(extra="forbid")

    stage_id: str = Field(..., description="Stage identifier: intent_routing, context_injection, action_execution, artifact_delivery, acceptance_verification")
    label: str = Field(..., description="Human readable stage title")
    status: str = Field(default="pending", description="Stage status: pending, in_progress, completed, failed, blocked")
    summary: str = Field(default="", description="Stage execution summary or observation snippet")
    timestamp: float | None = Field(default=None, description="Timestamp when stage was updated")


class InChatHandoffCardDTO(BaseModel):
    """Full snapshot of an in-chat bot handoff card with five-stage progress and approval gate."""

    model_config = ConfigDict(extra="forbid")

    handoff_id: str = Field(..., description="Unique handoff delegation identifier")
    session_id: str = Field(..., description="Active chat session identifier")
    source_agent: InChatAgentParticipantDTO = Field(..., description="Delegating source agent or user")
    target_agent: InChatAgentParticipantDTO = Field(..., description="Target recipient specialist bot")
    task_intent: str = Field(..., description="Concrete task intent and handover mandate")
    status: str = Field(default="pending", description="Overall handoff status: pending, awaiting_approval, in_progress, completed, rejected")
    requires_approval: bool = Field(default=False, description="Whether human approval gate is mandatory before pickup")
    stages: list[HandoffStageInfoDTO] = Field(default_factory=list, description="Ordered five-stage lifecycle states")
    deliverables: list[str] = Field(default_factory=list, description="Delivered artifact references or commit hashes")
    orchestrator_summary: str | None = Field(default=None, description="Unified orchestrator review summary")
    resume_context_note: str | None = Field(default=None, description="Optional weeks-later session pickup context reference")
    created_at: float = Field(default_factory=time.time, description="Creation epoch timestamp")
    updated_at: float = Field(default_factory=time.time, description="Last updated epoch timestamp")


class CreateInChatHandoffRequestDTO(BaseModel):
    """Request payload to initiate an in-chat agent delegation."""

    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(..., min_length=1, description="Chat session identifier")
    source_agent: InChatAgentParticipantDTO = Field(..., description="Source agent participant")
    target_agent: InChatAgentParticipantDTO = Field(..., description="Target specialist bot")
    task_intent: str = Field(..., min_length=1, description="Task delegation intent")
    requires_approval: bool = Field(default=False, description="Require approval before work pickup")
    resume_context_note: str | None = Field(default=None, description="Context pickup anchor note")


class HandoffActionRequestDTO(BaseModel):
    """Request payload for inline human gate or completion CTA."""

    model_config = ConfigDict(extra="forbid")

    action: str = Field(..., description="Action kind: approve, reject, send_to_pr, accept")
    actor_id: str = Field(default="user", description="Identifier of actor triggering the action")
    comment: str | None = Field(default=None, description="Optional comment or rejection feedback")


class HandoffAdvanceStageRequestDTO(BaseModel):
    """Request payload to update a stage within the five-stage stack."""

    model_config = ConfigDict(extra="forbid")

    stage_id: str = Field(..., min_length=1, description="Stage to update")
    status: str = Field(..., description="New stage status: pending, in_progress, completed, failed, blocked")
    summary: str = Field(default="", description="Summary or logs for this stage")
    orchestrator_summary: str | None = Field(default=None, description="Updated orchestrator review summary")
    deliverables: list[str] | None = Field(default=None, description="Incremental deliverable URLs or names")
