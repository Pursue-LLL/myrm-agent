"""
[POS] app/services/memory/memory_client_partition_service.py
[INPUT] app.schemas.memory_client_partition, myrm_agent_harness.toolkits.memory
[OUTPUT] MemoryClientPartitionService, get_memory_client_partition_service

Service coordinating client workspace path isolation and cross-client memory leakage screening.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from pathlib import Path

from myrm_agent_harness.toolkits.memory.client_partition import (
    ClientPartitionConfig,
    ClientWorkspaceResolver,
    CrossClientLeakGuard,
)
from myrm_agent_harness.toolkits.memory.types import (
    MemoryScope,
    MemorySearchResult,
    MemoryType,
    SemanticMemory,
)

from app.schemas.memory_client_partition import (
    ClientPartitionConfigDTO,
    ClientWorkspaceDescriptorDTO,
    CrossClientLeakViolationDTO,
    ScreenClientMemoriesRequestDTO,
    ScreenClientMemoriesResponseDTO,
)


def _to_harness_config(dto: ClientPartitionConfigDTO) -> ClientPartitionConfig:
    """Convert API ClientPartitionConfigDTO into harness ClientPartitionConfig."""
    return ClientPartitionConfig(
        client_id=dto.client_id,
        client_name=dto.client_name,
        workspace_root=dto.workspace_root,
        allow_global_read=dto.allow_global_read,
        strict_leak_check=dto.strict_leak_check,
    )


class MemoryClientPartitionService:
    """Service providing workspace isolation and cross-client memory screening."""

    def __init__(
        self,
        base_dir: Path | str | None = None,
        guard: CrossClientLeakGuard | None = None,
    ) -> None:
        self._base_dir = Path(base_dir).resolve() if base_dir else Path.cwd().resolve()
        self._resolver = ClientWorkspaceResolver(base_dir=self._base_dir)
        self._guard = guard or CrossClientLeakGuard()

    def resolve_client_workspace(
        self,
        dto: ClientPartitionConfigDTO,
        *,
        auto_create: bool = False,
    ) -> ClientWorkspaceDescriptorDTO:
        """Derive and validate an isolated workspace folder for target client."""
        harness_cfg = _to_harness_config(dto)
        descriptor = self._resolver.resolve_workspace(harness_cfg, auto_create=auto_create)
        return ClientWorkspaceDescriptorDTO(
            client_id=descriptor.client_id,
            relative_path=descriptor.relative_path,
            absolute_path=descriptor.absolute_path,
            is_isolated=descriptor.is_isolated,
        )

    def screen_client_memories(
        self, request: ScreenClientMemoriesRequestDTO
    ) -> ScreenClientMemoriesResponseDTO:
        """Screen memory recall candidates, purging any foreign client memories."""
        search_candidates: list[MemorySearchResult] = []
        for c in request.candidates:
            scope = MemoryScope(
                primary_namespace=c.primary_namespace,
                namespaces=list(c.namespaces) if c.namespaces else [c.primary_namespace],
                client_id=c.client_id,
            )
            memory = SemanticMemory(
                id=c.memory_id,
                content=c.content,
                scope=scope,
            )
            search_candidates.append(
                MemorySearchResult(
                    memory=memory,
                    memory_type=MemoryType.SEMANTIC,
                    score=c.score,
                )
            )

        safe_results, report = self._guard.screen_search_results(
            search_candidates,
            active_client_id=request.target_client_id,
            allow_global=request.allow_global,
        )

        violations_dto = [
            CrossClientLeakViolationDTO(
                target_client_id=v.target_client_id,
                offending_client_id=v.offending_client_id,
                offending_namespace=v.offending_namespace,
                memory_id=v.memory_id,
                reason=v.reason,
            )
            for v in report.violations
        ]

        safe_ids = [r.memory.id for r in safe_results]

        return ScreenClientMemoriesResponseDTO(
            target_client_id=report.target_client_id,
            total_evaluated=report.total_evaluated,
            allowed_count=report.allowed_count,
            filtered_count=report.filtered_count,
            safe_memory_ids=safe_ids,
            violations=violations_dto,
        )


_DEFAULT_SERVICE: MemoryClientPartitionService | None = None


def get_memory_client_partition_service() -> MemoryClientPartitionService:
    """Return default singleton MemoryClientPartitionService."""
    global _DEFAULT_SERVICE
    if _DEFAULT_SERVICE is None:
        _DEFAULT_SERVICE = MemoryClientPartitionService()
    return _DEFAULT_SERVICE
