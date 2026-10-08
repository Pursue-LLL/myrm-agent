"""Pydantic schemas and DTOs for Peer-Centric Social Cognition and Persona Card Suite (Item 110).

[INPUT]
- pydantic::{BaseModel, Field} (POS: validated request and response models)

[OUTPUT]
- PeerIdentityDTO, PeerRelationEdgeDTO, PeerPersonaCardDTO: peer identity, relation edge and persona card
- PeerCognitionProjectionDTO, GenerateProjectionRequest: low-token prompt projection of selected peers
- RegisterPeerRequest, AddRelationEdgeRequest, UpdatePersonaCardRequest, RecordInteractionRequest: write requests

[POS]
API contracts of peer social cognition and persona cards, shared by its router and service.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class PeerIdentityDTO(BaseModel):
    """Data transfer object for peer identity representation."""

    peer_id: str = Field(description="Unique system identifier for the peer")
    peer_type: str = Field(description="Participant category (user_peer, agent_peer, project_peer, reviewer_peer)")
    display_name: str = Field(description="Display label of peer")
    role_title: str = Field(default="", description="Functional role or job title")
    avatar_or_icon: str = Field(default="", description="Visual icon or avatar URI")
    created_at: str = Field(description="Creation ISO timestamp")
    last_seen_at: str = Field(description="Last interaction ISO timestamp")


class PeerRelationEdgeDTO(BaseModel):
    """Data transfer object for social cognition relation edges."""

    edge_id: str = Field(description="Unique edge identifier")
    source_peer_id: str = Field(description="Originating peer id")
    target_entity_id: str = Field(description="Target entity or peer id")
    target_is_peer: bool = Field(default=False, description="Whether target is another peer")
    relation_kind: str = Field(description="Semantic relational verb (asserts, approves, collaborates_with, governs)")
    context_note: str = Field(default="", description="Optional situational context or rationale")
    weight: float = Field(default=1.0, description="Confidence or strength weight between 0.0 and 1.0")
    created_at: str = Field(description="Creation ISO timestamp")


class PeerPersonaCardDTO(BaseModel):
    """Data transfer object for self-evolving standing persona card."""

    peer_id: str = Field(description="Associated peer identifier")
    peer_type: str = Field(description="Peer categorical type")
    display_name: str = Field(description="Display label of peer")
    core_responsibilities: list[str] = Field(
        default_factory=list, description="Primary duties, boundaries, or specialization areas"
    )
    decision_style: str = Field(
        default="balanced", description="Decision risk tolerance and behavioral style"
    )
    standing_preferences: dict[str, str] = Field(
        default_factory=dict, description="Persistent preference key-value pairs"
    )
    interaction_count: int = Field(default=0, description="Total recorded interactions")
    success_rate: float = Field(default=1.0, description="Collaborative task success rate")
    trust_score: float = Field(default=1.0, description="Trust evaluation score between 0.0 and 1.0")
    summary_digest: str = Field(
        default="", description="Compact natural language summary (<150 words) for zero-overhead prompt injection"
    )
    updated_at: str = Field(description="Last updated ISO timestamp")


class PeerCognitionProjectionDTO(BaseModel):
    """Data transfer object for low-token context prompt injection block."""

    formatted_prompt_block: str = Field(description="Rendered markdown block describing relevant peer profiles")
    token_cost_estimate: int = Field(default=0, description="Estimated token overhead of injected context")
    targeted_peers: list[str] = Field(default_factory=list, description="List of peer_ids included in projection")


class RegisterPeerRequest(BaseModel):
    """Request payload to register a new peer identity."""

    peer_id: str = Field(description="Unique system identifier for the peer")
    peer_type: str = Field(
        default="user_peer",
        description="Participant category: user_peer, agent_peer, project_peer, or reviewer_peer",
    )
    display_name: str = Field(description="Display label of peer")
    role_title: str = Field(default="", description="Functional role or job title")
    avatar_or_icon: str = Field(default="", description="Visual icon or avatar URI")


class AddRelationEdgeRequest(BaseModel):
    """Request payload to insert a relational edge into the social cognition graph."""

    edge_id: str = Field(description="Unique edge identifier")
    source_peer_id: str = Field(description="Originating peer id")
    target_entity_id: str = Field(description="Target entity or peer id")
    target_is_peer: bool = Field(default=False, description="Whether target is another peer")
    relation_kind: str = Field(
        default="asserts",
        description="Relational kind: asserts, approves, collaborates_with, governs, depends_on",
    )
    context_note: str = Field(default="", description="Optional context or rationale")
    weight: float = Field(default=1.0, description="Confidence or strength weight")


class UpdatePersonaCardRequest(BaseModel):
    """Request payload to create or mutate a persona card."""

    core_responsibilities: list[str] | None = Field(
        default=None, description="Primary duties, boundaries, or specialization areas"
    )
    decision_style: str | None = Field(default=None, description="Behavioral or decision style")
    standing_preferences: dict[str, str] | None = Field(
        default=None, description="Key-value preference updates"
    )
    summary_digest: str | None = Field(default=None, description="Explicit summary digest override")


class RecordInteractionRequest(BaseModel):
    """Request payload to evolve persona card upon interaction outcome."""

    success: bool = Field(description="Whether the collaborative task or turn succeeded")
    preference_deltas: dict[str, str] | None = Field(
        default=None, description="Optional new preference entries learned during interaction"
    )


class GenerateProjectionRequest(BaseModel):
    """Request payload to compile low-token context projection for a list of peers."""

    peer_ids: list[str] = Field(description="List of peer identifiers to compile into context")
