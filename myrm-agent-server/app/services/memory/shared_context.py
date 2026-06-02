"""
[INPUT]
app.database.connection::get_session (POS: 数据库会话工厂)
app.database.models::SharedContextModel (POS: 记忆域模型)

[OUTPUT]
SharedContextService: 共享上下文 CRUD、绑定解析和写入提案治理（goal_completion / correction_propagation 源幂等 dedup）
find_write_proposal_by_source: 按 source 查询已有写入提案
resolve_shared_context_ids: 运行时共享上下文绑定解析
shared_context_namespaces: SharedContext ID 到 Harness namespace 的转换

[POS]
共享上下文业务服务。负责把产品层 agent/channel/cron/conversation/task 绑定解析为
Harness 可理解的 `shared:<context_id>` namespace，并治理共享写入提案。
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Literal, cast

from nanoid import generate as nanoid
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.connection import get_session
from app.database.models import (
    SharedContextBindingModel,
    SharedContextModel,
    SharedContextWriteProposalModel,
)

SharedContextStatus = Literal["active", "archived"]
SharedContextTargetType = Literal["agent", "channel", "cron", "conversation", "task"]
SharedContextProposalStatus = Literal["pending", "approved", "rejected"]
SharedContextMemoryType = Literal["semantic", "episodic"]

_VALID_TARGET_TYPES: set[str] = {"agent", "channel", "cron", "conversation", "task"}
_VALID_CONTEXT_STATUSES: set[str] = {"active", "archived"}
_VALID_PROPOSAL_STATUSES: set[str] = {"pending", "approved", "rejected"}
_VALID_MEMORY_TYPES: set[str] = {"semantic", "episodic"}
_IDEMPOTENT_PROPOSAL_SOURCE_TYPES: frozenset[str] = frozenset(
    {"goal_completion", "correction_propagation"}
)
_DEFAULT_POLICY: dict[str, object] = {
    "write_mode": "proposal_required",
    "read_mode": "bound_targets",
    "correction_auto_approve": True,
    "goal_completion_auto_approve": True,
}
LEGACY_TEAM_CONTEXT_ID = "legacy-team"


def format_shared_context_namespace(context_id: str) -> str:
    """Return the Harness namespace for a SharedContext."""
    normalized = context_id.strip()
    if not normalized:
        raise ValueError("Shared context id is required")
    return f"shared:{normalized}"


def shared_context_namespaces(context_ids: Sequence[str]) -> list[str]:
    """Convert SharedContext IDs to deduplicated Harness namespaces."""
    return list(dict.fromkeys(format_shared_context_namespace(context_id) for context_id in context_ids))


def _normalize_required(value: str, *, field_name: str, max_length: int) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} is required")
    if len(normalized) > max_length:
        raise ValueError(f"{field_name} must be at most {max_length} characters")
    return normalized


def _normalize_optional(value: str | None, *, max_length: int) -> str:
    if value is None:
        return ""
    normalized = value.strip()
    if len(normalized) > max_length:
        raise ValueError(f"description must be at most {max_length} characters")
    return normalized


def _normalize_optional_field(value: str | None, *, field_name: str, max_length: int) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if len(normalized) > max_length:
        raise ValueError(f"{field_name} must be at most {max_length} characters")
    return normalized


def _validate_status(status: str) -> SharedContextStatus:
    if status not in _VALID_CONTEXT_STATUSES:
        raise ValueError(f"Invalid shared context status: {status}")
    return cast(SharedContextStatus, status)


def _validate_target_type(target_type: str) -> SharedContextTargetType:
    if target_type not in _VALID_TARGET_TYPES:
        raise ValueError(f"Invalid shared context binding target type: {target_type}")
    return cast(SharedContextTargetType, target_type)


def _validate_proposal_status(status: str) -> SharedContextProposalStatus:
    if status not in _VALID_PROPOSAL_STATUSES:
        raise ValueError(f"Invalid shared context proposal status: {status}")
    return cast(SharedContextProposalStatus, status)


def _validate_memory_type(memory_type: str) -> SharedContextMemoryType:
    if memory_type not in _VALID_MEMORY_TYPES:
        raise ValueError(f"Invalid shared context memory type: {memory_type}")
    return cast(SharedContextMemoryType, memory_type)


class SharedContextService:
    """Database-backed SharedContext domain service."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_contexts(self, *, status: SharedContextStatus | None = None) -> list[SharedContextModel]:
        stmt = select(SharedContextModel).order_by(SharedContextModel.created_at.desc())
        if status is not None:
            stmt = stmt.where(SharedContextModel.status == status)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_context(self, context_id: str) -> SharedContextModel | None:
        result = await self._session.execute(select(SharedContextModel).where(SharedContextModel.id == context_id))
        return cast(SharedContextModel | None, result.scalar_one_or_none())

    async def create_context(
        self,
        *,
        name: str,
        description: str | None = None,
        policy: dict[str, object] | None = None,
    ) -> SharedContextModel:
        context_id = nanoid(size=16)
        context = SharedContextModel(
            id=context_id,
            namespace=format_shared_context_namespace(context_id),
            name=_normalize_required(name, field_name="name", max_length=120),
            description=_normalize_optional(description, max_length=2000),
            status="active",
            policy=dict(policy or _DEFAULT_POLICY),
        )
        self._session.add(context)
        await self._session.commit()
        await self._session.refresh(context)
        return context

    async def get_or_create_legacy_team_context(self) -> SharedContextModel:
        """Return the deterministic context used for one-way legacy team memory migration."""
        existing = await self.get_context(LEGACY_TEAM_CONTEXT_ID)
        if existing is not None:
            return existing
        context = SharedContextModel(
            id=LEGACY_TEAM_CONTEXT_ID,
            namespace=format_shared_context_namespace(LEGACY_TEAM_CONTEXT_ID),
            name="Legacy Team Memory",
            description="One-way migration target for legacy team-visible memories.",
            status="active",
            policy={**_DEFAULT_POLICY, "migration_source": "legacy_team_memory"},
        )
        self._session.add(context)
        await self._session.commit()
        await self._session.refresh(context)
        return context

    async def update_context(
        self,
        context_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        status: SharedContextStatus | None = None,
        policy: dict[str, object] | None = None,
    ) -> SharedContextModel | None:
        context = await self.get_context(context_id)
        if context is None:
            return None
        if name is not None:
            context.name = _normalize_required(name, field_name="name", max_length=120)
        if description is not None:
            context.description = _normalize_optional(description, max_length=2000)
        if status is not None:
            context.status = _validate_status(status)
        if policy is not None:
            context.policy = dict(policy)
        await self._session.commit()
        await self._session.refresh(context)
        return context

    async def archive_context(self, context_id: str) -> SharedContextModel | None:
        return await self.update_context(context_id, status="archived")

    async def list_bindings(self, context_id: str) -> list[SharedContextBindingModel]:
        stmt = (
            select(SharedContextBindingModel)
            .where(SharedContextBindingModel.context_id == context_id)
            .order_by(SharedContextBindingModel.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_bindings_for_target(
        self,
        *,
        target_type: SharedContextTargetType,
        target_id: str,
    ) -> list[SharedContextBindingModel]:
        normalized_target_id = _normalize_required(target_id, field_name="target_id", max_length=255)
        stmt = (
            select(SharedContextBindingModel)
            .where(
                SharedContextBindingModel.target_type == _validate_target_type(target_type),
                SharedContextBindingModel.target_id == normalized_target_id,
            )
            .order_by(SharedContextBindingModel.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def bind_context(
        self,
        *,
        context_id: str,
        target_type: SharedContextTargetType,
        target_id: str,
    ) -> SharedContextBindingModel | None:
        context = await self.get_context(context_id)
        if context is None:
            return None
        normalized_target_id = _normalize_required(target_id, field_name="target_id", max_length=255)
        validated_target_type = _validate_target_type(target_type)
        existing = (
            await self._session.execute(
                select(SharedContextBindingModel).where(
                    SharedContextBindingModel.context_id == context_id,
                    SharedContextBindingModel.target_type == validated_target_type,
                    SharedContextBindingModel.target_id == normalized_target_id,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return cast(SharedContextBindingModel, existing)

        binding = SharedContextBindingModel(
            id=nanoid(size=16),
            context_id=context_id,
            target_type=validated_target_type,
            target_id=normalized_target_id,
        )
        self._session.add(binding)
        await self._session.commit()
        await self._session.refresh(binding)
        return binding

    async def unbind_context(self, *, context_id: str, binding_id: str) -> bool:
        binding = (
            await self._session.execute(
                select(SharedContextBindingModel).where(
                    SharedContextBindingModel.id == binding_id,
                    SharedContextBindingModel.context_id == context_id,
                )
            )
        ).scalar_one_or_none()
        if binding is None:
            return False
        await self._session.delete(binding)
        await self._session.commit()
        return True

    async def resolve_active_context_ids(
        self,
        targets: Sequence[tuple[SharedContextTargetType, str]],
    ) -> list[str]:
        normalized_targets = [
            (_validate_target_type(target_type), target_id.strip())
            for target_type, target_id in targets
            if target_id.strip()
        ]
        if not normalized_targets:
            return []

        clauses = [
            and_(
                SharedContextBindingModel.target_type == target_type,
                SharedContextBindingModel.target_id == target_id,
            )
            for target_type, target_id in normalized_targets
        ]
        stmt = (
            select(SharedContextBindingModel)
            .join(SharedContextModel, SharedContextBindingModel.context_id == SharedContextModel.id)
            .where(SharedContextModel.status == "active", or_(*clauses))
            .order_by(SharedContextBindingModel.created_at.asc())
        )
        result = await self._session.execute(stmt)
        bindings = list(result.scalars().all())
        target_order = {(target_type, target_id): index for index, (target_type, target_id) in enumerate(normalized_targets)}
        bindings.sort(
            key=lambda binding: (
                target_order.get(
                    (cast(SharedContextTargetType, binding.target_type), binding.target_id),
                    len(target_order),
                ),
                binding.created_at or datetime.min,
            )
        )
        return list(dict.fromkeys(binding.context_id for binding in bindings))

    async def find_write_proposal_by_source(
        self,
        *,
        context_id: str,
        source_type: str,
        source_id: str,
    ) -> SharedContextWriteProposalModel | None:
        normalized_source_type = _normalize_required(
            source_type, field_name="source_type", max_length=50
        )
        normalized_source_id = _normalize_required(
            source_id, field_name="source_id", max_length=255
        )
        result = await self._session.execute(
            select(SharedContextWriteProposalModel)
            .where(
                SharedContextWriteProposalModel.context_id == context_id,
                SharedContextWriteProposalModel.source_type == normalized_source_type,
                SharedContextWriteProposalModel.source_id == normalized_source_id,
            )
            .order_by(SharedContextWriteProposalModel.created_at.desc())
            .limit(1)
        )
        return cast(SharedContextWriteProposalModel | None, result.scalar_one_or_none())

    async def create_write_proposal(
        self,
        *,
        context_id: str,
        memory_type: SharedContextMemoryType,
        content: str,
        metadata: dict[str, object] | None = None,
        source_type: str = "manual",
        source_id: str | None = None,
    ) -> SharedContextWriteProposalModel | None:
        context = await self.get_context(context_id)
        if context is None:
            return None
        if context.status != "active":
            raise ValueError("Shared context is not active")
        normalized_source_type = _normalize_required(
            source_type, field_name="source_type", max_length=50
        )
        normalized_source_id = _normalize_optional_field(
            source_id, field_name="source_id", max_length=255
        )
        if (
            normalized_source_type in _IDEMPOTENT_PROPOSAL_SOURCE_TYPES
            and normalized_source_id
        ):
            existing = await self.find_write_proposal_by_source(
                context_id=context_id,
                source_type=normalized_source_type,
                source_id=normalized_source_id,
            )
            if existing is not None:
                return existing
        proposal = SharedContextWriteProposalModel(
            id=nanoid(size=16),
            context_id=context_id,
            memory_type=_validate_memory_type(memory_type),
            content=_normalize_required(content, field_name="content", max_length=4000),
            metadata_json=dict(metadata or {}),
            source_type=normalized_source_type,
            source_id=normalized_source_id,
            status="pending",
        )
        self._session.add(proposal)
        await self._session.commit()
        await self._session.refresh(proposal)
        return proposal

    async def list_write_proposals(
        self,
        *,
        context_id: str | None = None,
        status: SharedContextProposalStatus | None = None,
        limit: int = 100,
    ) -> list[SharedContextWriteProposalModel]:
        stmt = select(SharedContextWriteProposalModel).order_by(SharedContextWriteProposalModel.created_at.desc())
        if context_id is not None:
            stmt = stmt.where(SharedContextWriteProposalModel.context_id == context_id)
        if status is not None:
            stmt = stmt.where(SharedContextWriteProposalModel.status == _validate_proposal_status(status))
        result = await self._session.execute(stmt.limit(limit))
        return list(result.scalars().all())

    async def get_write_proposal(self, proposal_id: str) -> SharedContextWriteProposalModel | None:
        result = await self._session.execute(
            select(SharedContextWriteProposalModel).where(SharedContextWriteProposalModel.id == proposal_id)
        )
        return cast(SharedContextWriteProposalModel | None, result.scalar_one_or_none())

    async def update_write_proposal(
        self,
        proposal_id: str,
        *,
        content: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> SharedContextWriteProposalModel | None:
        proposal = await self.get_write_proposal(proposal_id)
        if proposal is None:
            return None
        if proposal.status != "pending":
            raise ValueError("Shared context write proposal is not pending")
        if content is not None:
            proposal.content = _normalize_required(content, field_name="content", max_length=4000)
        if metadata is not None:
            proposal.metadata_json = dict(metadata)
        await self._session.commit()
        await self._session.refresh(proposal)
        return proposal

    async def set_write_proposal_status(
        self,
        proposal_id: str,
        status: SharedContextProposalStatus,
    ) -> SharedContextWriteProposalModel | None:
        proposal = await self.get_write_proposal(proposal_id)
        if proposal is None:
            return None
        proposal.status = _validate_proposal_status(status)
        proposal.resolved_at = datetime.now(UTC)
        await self._session.commit()
        await self._session.refresh(proposal)
        return proposal


async def resolve_shared_context_ids(
    *,
    agent_id: str | None = None,
    channel_id: str | None = None,
    cron_id: str | None = None,
    conversation_id: str | None = None,
    task_id: str | None = None,
) -> list[str]:
    """Resolve active SharedContext IDs for a runtime memory binding."""
    targets: list[tuple[SharedContextTargetType, str]] = []
    if agent_id:
        targets.append(("agent", agent_id))
    if channel_id:
        targets.append(("channel", channel_id))
    if cron_id:
        targets.append(("cron", cron_id))
    if conversation_id:
        targets.append(("conversation", conversation_id))
    if task_id:
        targets.append(("task", task_id))

    async with get_session() as session:
        return await SharedContextService(session).resolve_active_context_ids(targets)
