"""Pydantic schemas for Diamond Topology Orchestrator & Blinded Adversarial Auditor."""

from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class DiamondStageEnum(str, Enum):
    """3 standard stages of Diamond topology."""

    FAN_OUT = "fan_out"
    REDUCE = "reduce"
    SYNTHESIZE = "synthesize"


class AuditorPerspectiveEnum(str, Enum):
    """Three independent review perspectives for blinded adversarial cross-validation."""

    FACT_ACCURACY = "fact_accuracy"
    TIMELINESS = "timeliness"
    CITATION_AUTHORITY = "citation_authority"


class RealityAnchorTypeEnum(str, Enum):
    """External objective reality signals that cannot be hallucinated or soft-degraded."""

    EXIT_CODE_ZERO = "exit_code_zero"
    HASH_MATCH = "hash_match"
    ROW_COUNT_MATCH = "row_count_match"


class RealityAnchorSpecDTO(BaseModel):
    """Binding specification for objective external verification."""

    anchor_type: RealityAnchorTypeEnum
    target_id: str
    expected_value: str
    actual_value: Optional[str] = None
    verified: bool = False


class AdversarialReviewItemDTO(BaseModel):
    """Individual review perspective output without CoT contamination."""

    perspective: AuditorPerspectiveEnum
    auditor_id: str
    passed: bool
    score: float
    critique: str
    isolated_context_verified: bool = True
    timestamp: float


class AdversarialVerdictDTO(BaseModel):
    """Consensus verdict from the blinded adversarial panel."""

    passed: bool
    total_reviews: int
    pass_count: int
    reviews: List[AdversarialReviewItemDTO] = Field(default_factory=list)
    anchor_checks: List[RealityAnchorSpecDTO] = Field(default_factory=list)
    consensus_summary: str = ""
    timestamp: float


class DiamondNodeDTO(BaseModel):
    """Node in the Diamond Topology DAG."""

    node_id: str
    title: str
    stage: DiamondStageEnum
    depends_on: List[str] = Field(default_factory=list)
    payload: Dict[str, str] = Field(default_factory=dict)
    output_artifact: Optional[str] = None
    cot_reasoning_internal: Optional[str] = None
    is_pruned: bool = False
    status: str = "pending"
    created_at: float


class CensusStatusDTO(BaseModel):
    """Census tracking for parallel fan-out dispatch to eliminate dead nodes."""

    dispatched_count: int
    received_count: int
    missing_nodes: List[str] = Field(default_factory=list)
    is_healthy: bool = True
    retried_nodes: List[str] = Field(default_factory=list)


class CreateDiamondPipelineRequest(BaseModel):
    """Payload to build a full diamond topology."""

    goal: str
    fan_out_specs: List[Dict[str, str]] = Field(default_factory=list)


class RecordNodeCompletionRequest(BaseModel):
    """Payload to record worker completion with internal CoT."""

    node_id: str
    output_artifact: str
    cot_reasoning_internal: Optional[str] = None
    success: bool = True


class AuditDeliveryRequest(BaseModel):
    """Blinded review request with objective reality anchors."""

    artifact: str
    reality_anchors: List[RealityAnchorSpecDTO] = Field(default_factory=list)
    pass_vote_ratio: float = 0.67


class SynthesizeRequest(BaseModel):
    """Payload to finalize synthesis stage."""

    summary_prefix: str = "Consolidated Architecture Synthesis:\n"


class PruneEdgesResponseDTO(BaseModel):
    """Pruned artificial serialized dependencies between fan-out nodes."""

    pruned_edges: List[List[str]] = Field(default_factory=list)
    remaining_nodes_count: int
