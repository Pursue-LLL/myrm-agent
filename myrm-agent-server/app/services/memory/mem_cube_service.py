# [POS]: app/services/memory/mem_cube_service.py
# [INPUT]: myrm_agent_harness.toolkits.memory, app.schemas.mem_cube
# [OUTPUT]: MemCubeService, get_mem_cube_service

"""Domain service for Memory Cube Scoped Isolation & Dynamic Mounting Suite (Item 124)."""

from __future__ import annotations

import datetime
import logging
import time

from myrm_agent_harness.toolkits.memory import (
    CubeMemoryRecord,
    CubeQueryRequest,
    CubeQueryResult,
    CubeScopeType,
    CubeWriteRequest,
    CubeWriteResult,
    MemoryCube,
    MemoryCubeOrchestrator,
    MountPolicy,
)

from app.schemas.mem_cube import (
    CreateCubeRequestDTO,
    CubeMatrixOverviewDTO,
    CubeQueryRequestDTO,
    CubeQueryResultDTO,
    CubeRecordDTO,
    CubeScopeTypeEnum,
    CubeWriteRequestDTO,
    CubeWriteResultDTO,
    MemoryCubeDTO,
    MountPolicyDTO,
    SetMountPolicyRequestDTO,
)

logger = logging.getLogger(__name__)


def _iso_to_timestamp(iso_str: str) -> float:
    try:
        dt = datetime.datetime.fromisoformat(iso_str)
        return dt.timestamp()
    except Exception:
        return time.time()


def _cube_domain_to_dto(domain: MemoryCube) -> MemoryCubeDTO:
    ts = _iso_to_timestamp(domain.created_at_iso)
    return MemoryCubeDTO(
        cube_id=domain.cube_id,
        name=domain.name,
        scope_type=CubeScopeTypeEnum(domain.scope_type.value),
        owner_id=domain.owner_id,
        description=domain.description,
        is_read_only=domain.is_read_only,
        item_count=domain.item_count,
        created_at=ts,
        updated_at=ts,
    )


def _policy_domain_to_dto(domain: MountPolicy) -> MountPolicyDTO:
    return MountPolicyDTO(
        agent_id=domain.agent_id,
        readable_cube_ids=list(domain.readable_cube_ids),
        writable_cube_ids=list(domain.writable_cube_ids),
        default_write_cube_id=domain.default_write_cube_id,
        strict_isolation=domain.strict_isolation,
    )


def _record_domain_to_dto(domain: CubeMemoryRecord) -> CubeRecordDTO:
    return CubeRecordDTO(
        record_id=domain.record_id,
        cube_id=domain.cube_id,
        content=domain.content,
        metadata=dict(domain.metadata),
        created_at=_iso_to_timestamp(domain.created_at_iso),
    )


class MemCubeService:
    """Service facade managing MemoryCube compartments, mount policies, and routed storage."""

    def __init__(self, orchestrator: MemoryCubeOrchestrator | None = None) -> None:
        self._orchestrator = orchestrator or MemoryCubeOrchestrator()
        self._bootstrap_default_topology()

    def _bootstrap_default_topology(self) -> None:
        if self._orchestrator.list_cubes():
            return
        self._orchestrator.create_cube(
            name="Global Core Principles",
            scope_type=CubeScopeType.GLOBAL_SHARED,
            cube_id="cube-global-shared",
            description="System-wide invariants, architecture rules, and core memory.",
            is_read_only=True,
        )
        self._orchestrator.write_to_cube(
            CubeWriteRequest(
                agent_id="system",
                target_cube_id="cube-global-shared",
                content="Architecture Rule: Enforce Clean Architecture and zero Any types.",
                importance=1.0,
            )
        )
        self._orchestrator.create_cube(
            name="OpenPerplexity Project Workspace",
            scope_type=CubeScopeType.PROJECT_WORKSPACE,
            cube_id="cube-proj-open-perplexity",
            owner_id="/workspace/open-perplexity",
            description="Project-level shared context, design specs, and roadmap notes.",
            is_read_only=False,
        )
        self._orchestrator.write_to_cube(
            CubeWriteRequest(
                agent_id="system",
                target_cube_id="cube-proj-open-perplexity",
                content="Workspace Context: Memory Cube suite addresses multi-agent cross-talk.",
                importance=0.9,
            )
        )
        self._orchestrator.create_cube(
            name="Architect Agent Private Journal",
            scope_type=CubeScopeType.AGENT_PRIVATE,
            cube_id="cube-agent-architect-private",
            owner_id="agent-architect",
            description="Private reflections, scratchpad notes, and working theories.",
            is_read_only=False,
        )
        self._orchestrator.mount_agent_cubes(
            agent_id="agent-architect",
            readable_cube_ids=[
                "cube-global-shared",
                "cube-proj-open-perplexity",
                "cube-agent-architect-private",
            ],
            writable_cube_ids=["cube-agent-architect-private"],
            default_write_cube_id="cube-agent-architect-private",
            strict_isolation=True,
        )

    def create_cube(self, req: CreateCubeRequestDTO) -> MemoryCubeDTO:
        domain_scope = CubeScopeType(req.scope_type.value)
        cube = self._orchestrator.create_cube(
            name=req.name,
            scope_type=domain_scope,
            owner_id=req.owner_id,
            description=req.description,
            is_read_only=req.is_read_only,
            cube_id=req.cube_id,
        )
        return _cube_domain_to_dto(cube)

    def get_cube(self, cube_id: str) -> MemoryCubeDTO | None:
        cube = self._orchestrator.get_cube(cube_id)
        return _cube_domain_to_dto(cube) if cube else None

    def list_cubes(
        self,
        scope_type: CubeScopeTypeEnum | None = None,
        owner_id: str | None = None,
    ) -> list[MemoryCubeDTO]:
        domain_scope = CubeScopeType(scope_type.value) if scope_type else None
        cubes = self._orchestrator.list_cubes(scope_type=domain_scope, owner_id=owner_id)
        return [_cube_domain_to_dto(c) for c in cubes]

    def delete_cube(self, cube_id: str) -> bool:
        return self._orchestrator.delete_cube(cube_id)

    def set_mount_policy(self, agent_id: str, req: SetMountPolicyRequestDTO) -> MountPolicyDTO:
        policy = self._orchestrator.mount_agent_cubes(
            agent_id=agent_id,
            readable_cube_ids=req.readable_cube_ids,
            writable_cube_ids=req.writable_cube_ids,
            default_write_cube_id=req.default_write_cube_id,
            strict_isolation=req.strict_isolation,
        )
        return _policy_domain_to_dto(policy)

    def get_mount_policy(self, agent_id: str) -> MountPolicyDTO | None:
        policy = self._orchestrator.router.get_policy(agent_id)
        return _policy_domain_to_dto(policy) if policy else None

    def list_all_policies(self) -> list[MountPolicyDTO]:
        policies = self._orchestrator.router.list_policies()
        return [_policy_domain_to_dto(p) for p in policies]

    def write_record(self, req: CubeWriteRequestDTO) -> CubeWriteResultDTO:
        str_metadata = {k: str(v) for k, v in req.metadata.items()}
        domain_req = CubeWriteRequest(
            agent_id=req.agent_id,
            content=req.content,
            target_cube_id=req.target_cube_id,
            metadata=str_metadata,
        )
        domain_res: CubeWriteResult = self._orchestrator.write_to_cube(domain_req)
        record_dto = _record_domain_to_dto(domain_res.record) if domain_res.record else None
        return CubeWriteResultDTO(
            success=domain_res.success,
            record=record_dto,
            destination_cube_id=domain_res.target_cube_id,
            rejection_reason=domain_res.rejection_reason,
        )

    def query_cubes(self, req: CubeQueryRequestDTO) -> CubeQueryResultDTO:
        start_time = time.perf_counter()
        domain_req = CubeQueryRequest(
            agent_id=req.agent_id,
            explicit_cube_ids=req.explicit_cube_ids,
            query=req.query,
            limit_per_cube=req.limit,
        )
        domain_res: CubeQueryResult = self._orchestrator.query_cubes(domain_req)
        duration_ms = (time.perf_counter() - start_time) * 1000.0

        all_items: list[CubeRecordDTO] = []
        for records in domain_res.records_by_cube.values():
            for rec in records:
                all_items.append(_record_domain_to_dto(rec))

        return CubeQueryResultDTO(
            items=all_items,
            total_found=domain_res.total_found,
            queried_cube_ids=list(domain_res.audited_cube_ids),
            query_duration_ms=round(duration_ms, 2),
        )

    def list_records(self, cube_id: str, limit: int = 50) -> list[CubeRecordDTO]:
        records = self._orchestrator.list_cube_records(cube_id, limit=limit)
        return [_record_domain_to_dto(r) for r in records]

    def write(self, req: CubeWriteRequestDTO) -> CubeWriteResultDTO:
        return self.write_record(req)

    def query(self, req: CubeQueryRequestDTO) -> CubeQueryResultDTO:
        return self.query_cubes(req)

    def get_matrix_overview(self) -> CubeMatrixOverviewDTO:
        cubes = self.list_cubes()
        policies = self.list_all_policies()
        total_records = sum(c.item_count for c in cubes)
        return CubeMatrixOverviewDTO(
            cubes=cubes,
            policies=policies,
            total_cubes=len(cubes),
            total_records=total_records,
            system_healthy=True,
        )


MemoryCubeService = MemCubeService
_mem_cube_service_instance: MemoryCubeService | None = None


def get_mem_cube_service() -> MemoryCubeService:
    global _mem_cube_service_instance
    if _mem_cube_service_instance is None:
        _mem_cube_service_instance = MemoryCubeService()
    return _mem_cube_service_instance


get_memory_cube_service = get_mem_cube_service
