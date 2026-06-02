"""Shared Context response serializers.

[INPUT]
app.api.memory.shared_context_schemas (POS: 共享上下文 API Schema 层)
app.database.models::SharedContextModel (POS: 记忆域模型)

[OUTPUT]
context_to_item: SharedContext ORM 到 API item 的转换
binding_to_item: SharedContext binding ORM 到 API item 的转换
proposal_to_item: SharedContext write proposal ORM 到 API item 的转换

[POS]
共享上下文 API 序列化辅助层。集中管理 ORM 到响应模型的无副作用转换。
"""

from __future__ import annotations

from typing import cast

from app.api.memory.shared_context_schemas import (
    SharedContextBindingItem,
    SharedContextItem,
    SharedContextMemoryType,
    SharedContextProposalStatus,
    SharedContextStatus,
    SharedContextTargetType,
    SharedContextWriteProposalItem,
)
from app.database.models import SharedContextBindingModel, SharedContextModel, SharedContextWriteProposalModel


def context_to_item(context: SharedContextModel) -> SharedContextItem:
    return SharedContextItem(
        id=context.id,
        namespace=context.namespace,
        name=context.name,
        description=context.description,
        status=cast(SharedContextStatus, context.status),
        policy=context.policy,
        created_at=context.created_at,
        updated_at=context.updated_at,
    )


def binding_to_item(binding: SharedContextBindingModel) -> SharedContextBindingItem:
    return SharedContextBindingItem(
        id=binding.id,
        context_id=binding.context_id,
        target_type=cast(SharedContextTargetType, binding.target_type),
        target_id=binding.target_id,
        created_at=binding.created_at,
    )


def proposal_to_item(proposal: SharedContextWriteProposalModel) -> SharedContextWriteProposalItem:
    return SharedContextWriteProposalItem(
        id=proposal.id,
        context_id=proposal.context_id,
        memory_type=cast(SharedContextMemoryType, proposal.memory_type),
        content=proposal.content,
        metadata=proposal.metadata_json or {},
        source_type=proposal.source_type,
        source_id=proposal.source_id,
        status=cast(SharedContextProposalStatus, proposal.status),
        created_at=proposal.created_at,
        resolved_at=proposal.resolved_at,
    )
