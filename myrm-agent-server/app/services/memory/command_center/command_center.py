"""Personal memory command center aggregation service.

[INPUT]
myrm_agent_harness.toolkits.memory::MemoryManager (POS: Unified memory manager and core facade of the Memory Toolkit)
app.services.memory.command_center.command_center_memory_scan::{count_memories_by_type, list_archived_memory_ids, list_pinned_memory_ids, list_active_memory_previews} (POS: 指挥中心对 MemoryManager 的只读扫描层)
app.services.memory.command_center.command_center_health::build_health (POS: 健康快照缓存与刷新)
app.services.memory.command_center.command_center_timeline::build_timeline (POS: 时间线投影)
app.services.memory.command_center.command_center_trace::build_trace_runs (POS: 召回追踪运行投影)
app.services.memory.command_center.command_center_replay::{build_replay, build_replay_events, build_waterfall} (POS: 回放与瀑布投影)
app.services.memory.command_center.command_center_recall_boundary::build_recall_boundary (POS: 召回边界与四分区预算快照)
app.services.memory.command_center.command_center_pending::{count_pending_review, build_pending_governance} (POS: 审批队列在指挥中心的读取视图)
app.database.models.memory::SharedContextModel (POS: 记忆域模型)
app.services.memory.shared_context.shared_context::SharedContextService (POS: 共享上下文业务服务)

[OUTPUT]
MemoryCommandCenterService: builds the single-user memory command center snapshot with optional project-scoped filtering.

[POS]
个人大脑指挥中心聚合服务。只负责编排：基于 MemoryManager、记忆治理 ORM 和部署设置组装设置页可观测快照，支持按项目过滤 SharedContext 记忆空间；
各区块的具体投影位于同目录的独立模块。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from myrm_agent_harness.toolkits.memory import MemoryManager, MemorySpaceKind
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.deploy_mode import get_deploy_mode, get_embedding_mode
from app.config.settings import settings
from app.database.models.memory import (
    SharedContextBindingModel,
    SharedContextModel,
    SharedContextWriteProposalModel,
)
from app.platform_utils.deployment_capabilities import get_deployment_capabilities
from app.schemas.memory.command_center import (
    MemoryCommandCenterResponse,
    MemoryCommandGovernanceItem,
    MemoryCommandHealth,
    MemoryCommandOverview,
    MemoryCommandRuntimeStatus,
    MemoryCommandSpace,
    MemoryRecallBoundaryData,
)
from app.services.memory.archive.restore.archive_restore import MemoryArchiveRestoreService
from app.services.memory.command_center.command_center_economics import MemoryEconomicsService
from app.services.memory.command_center.command_center_health import build_health
from app.services.memory.command_center.command_center_insights import MemoryCommandCenterInsights
from app.services.memory.command_center.command_center_memory_scan import (
    count_memories_by_type,
    list_active_memory_previews,
    list_archived_memory_ids,
    list_pinned_memory_ids,
)
from app.services.memory.command_center.command_center_pending import build_pending_governance, count_pending_review
from app.services.memory.command_center.command_center_projection_utils import preview_content, restrict_to_context_ids
from app.services.memory.command_center.command_center_recall_boundary import build_recall_boundary
from app.services.memory.command_center.command_center_replay import build_replay, build_replay_events, build_waterfall
from app.services.memory.command_center.command_center_timeline import build_timeline
from app.services.memory.command_center.command_center_trace import build_trace_runs
from app.services.memory.diagnostics.diagnostics import MemoryDiagnosticsService
from app.services.memory.imports.import_ledger import MemoryImportLedgerService
from app.services.memory.ledger.operation_ledger import MemoryOperationLedgerService

_SPACE_LIMIT = 20
_PROPOSAL_GOVERNANCE_LIMIT = 5
_GOVERNANCE_LIMIT = 8
_LIVE_STREAM_LIMIT = 12
_ECONOMICS_TURN_LIMIT = 50


class MemoryCommandCenterService:
    """Builds the single-user memory command center snapshot."""

    def __init__(
        self,
        db: AsyncSession,
        memory_manager: MemoryManager,
        *,
        project_id: str | None = None,
    ) -> None:
        self._db = db
        self._memory_manager = memory_manager
        self._project_id = project_id
        self._project_context_ids: set[str] | None = None
        self._ledger = MemoryOperationLedgerService(db)
        self._import_ledger = MemoryImportLedgerService(db)
        self._insights = MemoryCommandCenterInsights(db, memory_manager, self._ledger)
        self._diagnostics = MemoryDiagnosticsService(db, memory_manager, ledger=self._ledger)

    async def _resolve_project_context_ids(self) -> set[str] | None:
        """Resolve SharedContext IDs bound to the given project, or None for global view."""
        if self._project_id is None:
            return None
        if self._project_context_ids is not None:
            return self._project_context_ids
        from app.services.memory.shared_context.shared_context import (
            SharedContextService,
        )

        svc = SharedContextService(self._db)
        bindings = await svc.list_bindings_for_target(target_type="project", target_id=self._project_id)
        self._project_context_ids = {b.context_id for b in bindings}
        return self._project_context_ids

    async def get_archived_memory_ids(self) -> set[str]:
        return await list_archived_memory_ids(self._memory_manager)

    async def get_pinned_memory_ids(self) -> set[str]:
        return await list_pinned_memory_ids(self._memory_manager)

    async def get_active_memory_previews(self) -> dict[str, tuple[str, str]]:
        return await list_active_memory_previews(self._memory_manager)

    async def build_snapshot(self) -> MemoryCommandCenterResponse:
        generated_at = datetime.now(UTC)
        by_type = await count_memories_by_type(self._memory_manager)
        pending_memories = await count_pending_review(self._db, self._memory_manager)
        pending_shared_proposals = await self._count_rows(
            select(func.count())
            .select_from(SharedContextWriteProposalModel)
            .where(SharedContextWriteProposalModel.status == "pending")
        )
        active_shared_contexts = await self._count_rows(
            select(func.count()).select_from(SharedContextModel).where(SharedContextModel.status == "active")
        )
        health = await self._build_health()
        deploy_mode = get_deploy_mode().value
        timeline = await build_timeline(
            db=self._db,
            ledger=self._ledger,
            memory_manager=self._memory_manager,
            project_context_ids=await self._resolve_project_context_ids(),
        )
        influence = await self._insights.build_influence()
        economics = await MemoryEconomicsService(self._db).build_economics_dashboard(
            influence=influence,
            archived_memory_ids=await self.get_archived_memory_ids(),
            pinned_memory_ids=await self.get_pinned_memory_ids(),
            memory_previews=await self.get_active_memory_previews(),
            limit_turns=_ECONOMICS_TURN_LIMIT,
        )
        cost = economics.cost_profile
        governance = await self._build_governance()
        conflicts = await self._insights.build_conflicts()
        migration = await self._insights.build_migration()
        import_rollback_health = await self._import_ledger.rollback_health()
        archive_restore_health = await MemoryArchiveRestoreService(self._db).restore_health()
        runtime = self._build_runtime(deploy_mode)

        overview = MemoryCommandOverview(
            total_memories=sum(by_type.values()),
            by_type=by_type,
            pending_memories=pending_memories,
            pending_shared_proposals=pending_shared_proposals,
            active_shared_contexts=active_shared_contexts,
            health_score=health.total,
            health_status=health.status,
            deploy_mode=deploy_mode,
        )

        return MemoryCommandCenterResponse(
            generated_at=generated_at,
            overview=overview,
            spaces=await self._build_spaces(),
            governance=governance,
            health=health,
            timeline=timeline,
            live_stream=timeline[:_LIVE_STREAM_LIMIT],
            influence=influence,
            cost=cost,
            economics=economics,
            conflicts=conflicts,
            replay=build_replay(timeline, influence),
            replay_events=build_replay_events(timeline),
            waterfall=build_waterfall(timeline, influence, cost),
            trace_runs=build_trace_runs(timeline),
            eval_metrics=self._insights.build_eval_metrics(
                timeline=timeline,
                influence=influence,
                conflicts=conflicts,
                migration=migration,
            ),
            connectors=self._insights.build_connectors(),
            privacy=self._insights.build_privacy_signals(timeline),
            doctor_checks=await self._diagnostics.build_doctor_checks(
                health_cache_status=health.cache_status,
                runtime=runtime,
            ),
            migration=migration,
            plane_summary=self._insights.build_plane_summary(
                health_status=health.status,
                timeline=timeline,
                governance_backlog=len(governance),
                import_rollback_health=import_rollback_health,
                archive_restore_health=archive_restore_health,
            ),
            runtime=runtime,
        )

    async def build_recall_boundary_snapshot(
        self,
        *,
        agent_id: str | None = None,
        task_id: str | None = None,
    ) -> MemoryRecallBoundaryData:
        """Build review-first memory recall boundary and candidate/approved partition snapshot."""
        return await build_recall_boundary(self._db, self._memory_manager, agent_id=agent_id, task_id=task_id)

    async def refresh_health(self) -> MemoryCommandHealth:
        return await self._build_health(force_refresh=True)

    async def _build_health(self, *, force_refresh: bool = False) -> MemoryCommandHealth:
        return await build_health(
            db=self._db,
            ledger=self._ledger,
            memory_manager=self._memory_manager,
            force_refresh=force_refresh,
        )

    async def _build_spaces(self) -> list[MemoryCommandSpace]:
        project_ctx_ids = await self._resolve_project_context_ids()

        spaces: list[MemoryCommandSpace] = (
            [
                MemoryCommandSpace(
                    namespace=namespace,
                    kind=self._space_kind(namespace).value,
                    label=self._space_label(namespace),
                    active=True,
                )
                for namespace in self._memory_manager.namespaces
            ]
            if project_ctx_ids is None
            else []
        )

        binding_counts = await self._shared_context_binding_counts()
        statement = restrict_to_context_ids(
            select(SharedContextModel).order_by(SharedContextModel.updated_at.desc()).limit(_SPACE_LIMIT),
            SharedContextModel.id,
            project_ctx_ids,
        )
        for context in (await self._db.execute(statement)).scalars().all():
            spaces.append(
                MemoryCommandSpace(
                    namespace=context.namespace,
                    kind=MemorySpaceKind.SHARED.value,
                    label=context.name,
                    context_id=context.id,
                    active=context.status == "active",
                    binding_count=binding_counts.get(context.id, 0),
                )
            )
        return spaces

    async def _build_governance(self) -> list[MemoryCommandGovernanceItem]:
        items: list[MemoryCommandGovernanceItem] = []
        project_ctx_ids = await self._resolve_project_context_ids()

        if project_ctx_ids is None:
            items.extend(await build_pending_governance(self._memory_manager))

        statement = restrict_to_context_ids(
            select(SharedContextWriteProposalModel)
            .where(SharedContextWriteProposalModel.status == "pending")
            .order_by(SharedContextWriteProposalModel.created_at.desc())
            .limit(_PROPOSAL_GOVERNANCE_LIMIT),
            SharedContextWriteProposalModel.context_id,
            project_ctx_ids,
        )
        for proposal in (await self._db.execute(statement)).scalars().all():
            items.append(
                MemoryCommandGovernanceItem(
                    id=proposal.id,
                    kind="shared_context_proposal",
                    target_kind="shared_context_proposal",
                    title=proposal.memory_type,
                    description=preview_content(proposal.content),
                    severity="warning",
                    status=proposal.status,
                    created_at=proposal.created_at,
                    available_actions=["approve", "reject", "edit"],
                )
            )

        items.sort(key=lambda item: item.created_at, reverse=True)
        return items[:_GOVERNANCE_LIMIT]

    def _build_vector_persistence(
        self,
    ) -> Literal["persistent", "memory_fallback", "unavailable"]:
        """Vector store persistence state for the runtime panel.

        Reflects whether vector memories survive restarts: an embedded store
        that degraded to ``:memory:`` reports ``"memory_fallback"`` so the UI
        can warn instead of implying durable storage.
        """
        if not self._memory_manager.has_vector:
            return "unavailable"
        return "persistent" if self._memory_manager.vector_is_persistent else "memory_fallback"

    def _build_runtime(self, deploy_mode: str) -> MemoryCommandRuntimeStatus:
        return MemoryCommandRuntimeStatus(
            deploy_mode=deploy_mode,
            memory_base_path=settings.database.memory_base_path,
            relational_status=("available" if self._memory_manager.has_relational else "unavailable"),
            vector_status=("available" if self._memory_manager.has_vector else "unavailable"),
            vector_persistence=self._build_vector_persistence(),
            graph_status=("available" if self._memory_manager.has_graph else "unavailable"),
            embedding_status=(get_embedding_mode().value if self._memory_manager.has_vector else "unavailable"),
            # Without an embedding backend semantic and episodic memories are
            # served by the BM25 sparse mirror: keyword recall, not semantics.
            retrieval_mode=("semantic" if self._memory_manager.has_vector else "keyword"),
            control_plane_status=("proxied_by_sandbox" if get_deployment_capabilities().is_sandbox_instance else "not_used"),
            event_ledger_status="available",
            health_snapshot_status="available",
            supported_clients=["local_web", "tauri_desktop", "saas_sandbox"],
        )

    async def _shared_context_binding_counts(self) -> dict[str, int]:
        result = await self._db.execute(
            select(
                SharedContextBindingModel.context_id,
                func.count(SharedContextBindingModel.id),
            ).group_by(SharedContextBindingModel.context_id)
        )
        return {str(context_id): int(count or 0) for context_id, count in result.all()}

    async def _count_rows(self, statement: Select[int]) -> int:
        result = await self._db.execute(statement)
        return int(result.scalar_one() or 0)

    @staticmethod
    def _space_kind(namespace: str) -> MemorySpaceKind:
        try:
            return MemorySpaceKind(namespace.split(":", 1)[0])
        except ValueError:
            return MemorySpaceKind.UNKNOWN

    @staticmethod
    def _space_label(namespace: str) -> str:
        if ":" not in namespace:
            return namespace
        kind, value = namespace.split(":", 1)
        return f"{kind} / {value}"
