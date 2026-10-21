"""Pydantic schemas for Multi-Human Multi-Agent Live Document Co-Authoring Ledger."""

from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class CollaboratorTypeEnum(str, Enum):
    """Classification: human participant or AI agent."""

    HUMAN = "human"
    AGENT = "agent"


class BlockTypeEnum(str, Enum):
    """Semantic block type."""

    HEADING = "heading"
    PARAGRAPH = "paragraph"
    CODE = "code"
    TABLE = "table"
    BULLET_LIST = "bullet_list"


class DeltaOperationEnum(str, Enum):
    """Atomic delta operations."""

    INSERT_BLOCK = "insert_block"
    UPDATE_BLOCK = "update_block"
    DELETE_BLOCK = "delete_block"
    REORDER_BLOCKS = "reorder_blocks"


class ArbitrationStrategyEnum(str, Enum):
    """Conflict arbitration strategies."""

    HUMAN_PRIORITY = "human_priority"
    TIMESTAMP_LWW = "timestamp_lww"
    ISOLATED_STAGING_PROPOSAL = "isolated_staging_proposal"


class CollaboratorProfileDTO(BaseModel):
    """Collaborator profile representation."""

    collaborator_id: str
    collaborator_type: CollaboratorTypeEnum
    name: str
    principal_human_id: Optional[str] = None
    role_description: str = ""
    joined_at: float


class DocumentBlockDTO(BaseModel):
    """Granular live block in co-authored document."""

    block_id: str
    block_type: BlockTypeEnum
    content: str
    version: int = 1
    last_author_id: str = ""
    last_updated_at: float
    lease_holder_id: Optional[str] = None
    lease_expires_at: Optional[float] = None


class DeltaEntryDTO(BaseModel):
    """Immutable ledger entry with intent attribution."""

    delta_id: str
    document_id: str
    block_id: str
    operation: DeltaOperationEnum
    author_id: str
    author_type: CollaboratorTypeEnum
    principal_human_id: Optional[str] = None
    prev_content: str = ""
    new_content: str = ""
    intent_reason: str = ""
    timestamp: float
    applied: bool = True


class StagingProposalDTO(BaseModel):
    """Isolated staging proposal."""

    proposal_id: str
    block_id: str
    author_id: str
    content: str
    intent_reason: str
    status: str = "pending"
    created_at: float


class ConflictRecordDTO(BaseModel):
    """Conflict audit record."""

    conflict_id: str
    block_id: str
    competing_authors: List[str] = Field(default_factory=list)
    detected_at: float
    resolved: bool = False
    resolution_strategy: ArbitrationStrategyEnum
    resolution_summary: str = ""


class ArbitrationVerdictDTO(BaseModel):
    """Arbitration consensus verdict."""

    resolved: bool
    winning_content: str
    strategy: ArbitrationStrategyEnum
    summary: str
    staging_proposals: List[StagingProposalDTO] = Field(default_factory=list)
    timestamp: float


class RegisterCollaboratorRequest(BaseModel):
    """Register collaborator payload."""

    collaborator_id: str
    collaborator_type: CollaboratorTypeEnum
    name: str
    principal_human_id: Optional[str] = None
    role_description: str = ""


class InitDocumentRequest(BaseModel):
    """Initialize live document payload."""

    document_id: str
    title: str = "Untitled Collaborative Doc"
    blocks: List[DocumentBlockDTO] = Field(default_factory=list)


class AcquireLeaseRequest(BaseModel):
    """Acquire lease payload."""

    block_id: str
    author_id: str
    duration_seconds: float = 30.0


class ReleaseLeaseRequest(BaseModel):
    """Release lease payload."""

    block_id: str
    author_id: str


class ApplyDeltaRequest(BaseModel):
    """Apply delta mutation payload."""

    block_id: str
    operation: DeltaOperationEnum
    author_id: str
    new_content: str
    intent_reason: str = ""
    block_type: BlockTypeEnum = BlockTypeEnum.PARAGRAPH


class ArbitrateConflictRequest(BaseModel):
    """Arbitrate competing update payload."""

    block_id: str
    first_author_id: str
    first_content: str
    first_reason: str
    second_author_id: str
    second_content: str
    second_reason: str
    strategy: ArbitrationStrategyEnum = ArbitrationStrategyEnum.HUMAN_PRIORITY


class AcceptProposalRequest(BaseModel):
    """Accept and merge proposal payload."""

    reviewer_id: str
