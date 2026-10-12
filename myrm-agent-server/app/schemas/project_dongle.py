"""Pydantic schemas for Project Context USB Dongle and cross-agent relay protocol.

[INPUT]
- Workspace directory, bullet block objects, sync payloads, and prompt requests.

[OUTPUT]
- DongleBlockDTO, DongleArchivePointerDTO, DongleStateDTO, DongleInitRequestDTO,
  DongleInitResponseDTO, DongleSyncRequestDTO, DongleSyncResponseDTO, DongleContextPromptResponseDTO.

[POS]
- Server-side DTO contracts for Item 152 ProjectContextUsbDongleAndCrossAgentRelaySuite.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class DongleBlockDTO(BaseModel):
    """Data transfer object for a single memory bullet block."""

    block_id: str = Field(..., description="Unique block identifier")
    block_type: str = Field(..., description="Target file: PROJECT_STATE.md, DECISIONS.md, LESSONS.md, INDEX.md")
    content: str = Field(..., description="Content of the bullet block")
    created_date: str = Field(..., description="Date string YYYY-MM-DD")
    status: str = Field(default="active", description="Block status")
    tags: list[str] = Field(default_factory=list, description="Associated tag labels")


class DongleArchivePointerDTO(BaseModel):
    """Pointer line referencing an overflowed block archived in a separate file."""

    block_id: str = Field(..., description="ID of the archived block")
    date_str: str = Field(..., description="Original creation date YYYY-MM-DD")
    summary: str = Field(..., description="Brief summary of the archived block")
    target_archive_file: str = Field(..., description="Archive filename where full block resides")


class DongleStateDTO(BaseModel):
    """Full snapshot of the 4-tier project memory dongle in a workspace."""

    workspace_dir: str
    project_state_blocks: list[DongleBlockDTO] = Field(default_factory=list)
    decision_blocks: list[DongleBlockDTO] = Field(default_factory=list)
    lesson_blocks: list[DongleBlockDTO] = Field(default_factory=list)
    index_content: str = ""
    archive_pointers: list[DongleArchivePointerDTO] = Field(default_factory=list)
    total_active_blocks: int = 0


class DongleInitRequestDTO(BaseModel):
    """Payload to initialize standard 4-tier memory files in a workspace."""

    workspace_dir: str = Field(..., description="Workspace root directory path")


class DongleInitResponseDTO(BaseModel):
    """Result of initializing standard memory files."""

    workspace_dir: str
    initialized_files: list[str] = Field(default_factory=list)
    message: str


class DongleSyncRequestDTO(BaseModel):
    """Payload to batch sync blocks into the project memory dongle."""

    workspace_dir: str = Field(..., description="Workspace root directory path")
    blocks: list[DongleBlockDTO] = Field(..., description="Blocks to append or synchronize")


class DongleSyncResponseDTO(BaseModel):
    """Result of synchronizing memory blocks with potential archive spilling."""

    updated_files: list[str] = Field(default_factory=list)
    added_blocks_count: int
    spilled_blocks_count: int
    created_pointers: list[DongleArchivePointerDTO] = Field(default_factory=list)
    message: str


class DongleContextPromptResponseDTO(BaseModel):
    """Rendered Layer 1 deterministic system prompt context for zero-loss relay."""

    workspace_dir: str
    prompt_context: str
