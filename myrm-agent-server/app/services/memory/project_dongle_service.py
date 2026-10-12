"""Service coordinating Project Context USB Dongle operations.

[INPUT]
- Workspace paths, DongleBlockDTO items, DTO requests.

[OUTPUT]
- ProjectDongleService: initializes workspace dongle, loads states, syncs blocks, and produces Layer 1 prompts.

[POS]
- Server-side business service for Item 152 ProjectContextUsbDongleAndCrossAgentRelaySuite.
"""

from __future__ import annotations

from pathlib import Path

from myrm_agent_harness.toolkits.memory.project_dongle import (
    DongleBlock,
    DongleBlockType,
    ProjectContextDongleManager,
)

from app.schemas.project_dongle import (
    DongleArchivePointerDTO,
    DongleBlockDTO,
    DongleContextPromptResponseDTO,
    DongleInitResponseDTO,
    DongleStateDTO,
    DongleSyncResponseDTO,
)


class ProjectDongleService:
    """Business service for Project Context USB Dongle and cross-agent relay."""

    def __init__(self, dongle_manager: ProjectContextDongleManager | None = None) -> None:
        self.dongle_manager = dongle_manager or ProjectContextDongleManager()

    def init_workspace(self, workspace_dir: str) -> DongleInitResponseDTO:
        """Initialize the 4-tier memory files in workspace if they do not exist."""
        ws_path = Path(workspace_dir)
        initialized = self.dongle_manager.ensure_initialized(ws_path)
        return DongleInitResponseDTO(
            workspace_dir=workspace_dir,
            initialized_files=initialized,
            message=f"Initialized {len(initialized)} memory files in workspace.",
        )

    def get_state(self, workspace_dir: str) -> DongleStateDTO:
        """Fetch and aggregate the current 4-tier memory state from disk."""
        ws_path = Path(workspace_dir)
        state = self.dongle_manager.load_state(ws_path)

        def _map_blocks(blocks: tuple[DongleBlock, ...]) -> list[DongleBlockDTO]:
            return [
                DongleBlockDTO(
                    block_id=b.block_id,
                    block_type=b.block_type.value,
                    content=b.content,
                    created_date=b.created_date,
                    status=b.status,
                    tags=list(b.tags),
                )
                for b in blocks
            ]

        pointers_dto = [
            DongleArchivePointerDTO(
                block_id=p.block_id,
                date_str=p.date_str,
                summary=p.summary,
                target_archive_file=p.target_archive_file,
            )
            for p in state.archive_pointers
        ]

        ps_blocks = _map_blocks(state.project_state_blocks)
        dec_blocks = _map_blocks(state.decision_blocks)
        les_blocks = _map_blocks(state.lesson_blocks)

        return DongleStateDTO(
            workspace_dir=state.workspace_dir,
            project_state_blocks=ps_blocks,
            decision_blocks=dec_blocks,
            lesson_blocks=les_blocks,
            index_content=state.index_content,
            archive_pointers=pointers_dto,
            total_active_blocks=len(ps_blocks) + len(dec_blocks) + len(les_blocks),
        )

    def get_context_prompt(self, workspace_dir: str) -> DongleContextPromptResponseDTO:
        """Render deterministic Layer 1 prompt text for zero-loss relay."""
        ws_path = Path(workspace_dir)
        state = self.dongle_manager.load_state(ws_path)
        prompt = self.dongle_manager.render_context_prompt(state)
        return DongleContextPromptResponseDTO(
            workspace_dir=workspace_dir,
            prompt_context=prompt,
        )

    def sync_blocks(self, workspace_dir: str, block_dtos: list[DongleBlockDTO]) -> DongleSyncResponseDTO:
        """Synchronize new blocks into the workspace memory dongle."""
        ws_path = Path(workspace_dir)
        domain_blocks: list[DongleBlock] = []

        type_map = {
            DongleBlockType.PROJECT_STATE.value: DongleBlockType.PROJECT_STATE,
            DongleBlockType.DECISIONS.value: DongleBlockType.DECISIONS,
            DongleBlockType.LESSONS.value: DongleBlockType.LESSONS,
            DongleBlockType.INDEX.value: DongleBlockType.INDEX,
        }

        for dto in block_dtos:
            b_type = type_map.get(dto.block_type, DongleBlockType.PROJECT_STATE)
            domain_blocks.append(
                DongleBlock(
                    block_id=dto.block_id,
                    block_type=b_type,
                    content=dto.content,
                    created_date=dto.created_date,
                    status=dto.status,
                    tags=tuple(dto.tags),
                )
            )

        res = self.dongle_manager.sync_batch(ws_path, domain_blocks)
        created_ptrs_dto = [
            DongleArchivePointerDTO(
                block_id=p.block_id,
                date_str=p.date_str,
                summary=p.summary,
                target_archive_file=p.target_archive_file,
            )
            for p in res.created_pointers
        ]

        return DongleSyncResponseDTO(
            updated_files=list(res.updated_files),
            added_blocks_count=res.added_blocks_count,
            spilled_blocks_count=res.spilled_blocks_count,
            created_pointers=created_ptrs_dto,
            message=res.message,
        )
