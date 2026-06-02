"""Shared Context migration operations.

[INPUT]
app.api.memory.shared_context_schemas::LegacyTeamMemoryMigrationResponse (POS: 共享上下文 API Schema 层)
app.services.memory.shared_context::SharedContextService (POS: 共享上下文业务服务)
app.core.memory.adapters.setup::create_memory_manager (POS: 业务层记忆适配器入口)

[OUTPUT]
router: legacy team-visible memory 到 Shared Context 的一次性迁移端点

[POS]
共享上下文迁移 API 操作层。只负责非破坏性迁移 legacy `visibility/team_id` 记忆到 `shared:legacy-team`。
"""

from __future__ import annotations

from typing import cast

from fastapi import APIRouter, Depends
from myrm_agent_harness.toolkits.memory import MemoryManager
from myrm_agent_harness.toolkits.memory.types import EpisodicMemory, SemanticMemory
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session
from app.api.memory.operations.shared_context_serializers import context_to_item
from app.api.memory.shared_context_schemas import LegacyTeamMemoryMigrationResponse
from app.api.memory.utils import get_crud_memory_manager
from app.core.memory.adapters.setup import create_memory_manager, resolve_memory_binding
from app.services.memory.shared_context import SharedContextService

router = APIRouter(prefix="/shared-contexts")


def _entry_metadata(entry: dict[str, object]) -> dict[str, object]:
    metadata = entry.get("metadata")
    return dict(cast(dict[str, object], metadata)) if isinstance(metadata, dict) else {}


def _is_legacy_team_entry(entry: dict[str, object]) -> bool:
    metadata = _entry_metadata(entry)
    return entry.get("visibility") == "team" or metadata.get("visibility") == "team" or bool(metadata.get("team_id"))


def _clean_legacy_metadata(entry: dict[str, object]) -> dict[str, str | int | float | bool]:
    metadata = _entry_metadata(entry)
    cleaned: dict[str, str | int | float | bool] = {"migrated_from_team_memory": True}
    for key, value in metadata.items():
        if key in {"visibility", "team_id"}:
            continue
        if isinstance(value, str | int | float | bool):
            cleaned[key] = value
    legacy_team_id = metadata.get("team_id") or entry.get("team_id")
    if isinstance(legacy_team_id, str) and legacy_team_id:
        cleaned["legacy_team_id"] = legacy_team_id
    return cleaned


def _entry_float(entry: dict[str, object], key: str, default: float) -> float:
    value = entry.get(key)
    return float(value) if isinstance(value, int | float) else default


def _entry_str(entry: dict[str, object], key: str) -> str | None:
    value = entry.get(key)
    return value if isinstance(value, str) and value else None


def _entry_str_list(entry: dict[str, object], key: str) -> list[str]:
    value = entry.get(key)
    return [str(item) for item in value] if isinstance(value, list) else []


@router.post("/migrate-legacy-team", response_model=LegacyTeamMemoryMigrationResponse)
async def migrate_legacy_team_memories(
    db: AsyncSession = Depends(get_db_session),
    source_manager: MemoryManager = Depends(get_crud_memory_manager),
) -> LegacyTeamMemoryMigrationResponse:
    """Copy legacy team-visible memories into the deterministic Legacy Team Shared Context."""
    service = SharedContextService(db)
    context = await service.get_or_create_legacy_team_context()

    from app.services.agent.platform_config import require_platform_embedding_config

    embedding_cfg = await require_platform_embedding_config()

    shared_manager = await create_memory_manager(
        resolve_memory_binding(
            namespaces=[context.namespace],
            agent_id="shared-context",
            channel_id=None,
            conversation_id=None,
            task_id=None,
        ),
        embedding_cfg,
        approval_required=False,
    )

    exported = await source_manager.export_all()
    semantic_memories: list[SemanticMemory] = []
    episodic_memories: list[EpisodicMemory] = []
    skipped = 0

    for entry in exported.get("semantic", []):
        if not _is_legacy_team_entry(entry):
            skipped += 1
            continue
        semantic_memories.append(
            SemanticMemory(
                content=str(entry.get("content", "")),
                importance=_entry_float(entry, "importance", 0.5),
                confidence=_entry_float(entry, "confidence", 1.0),
                source_chat_id=_entry_str(entry, "source_chat_id"),
                source_message_id=_entry_str(entry, "source_message_id"),
                tags=_entry_str_list(entry, "tags"),
                metadata=_clean_legacy_metadata(entry),
            )
        )

    for entry in exported.get("episodic", []):
        if not _is_legacy_team_entry(entry):
            skipped += 1
            continue
        episodic_memories.append(
            EpisodicMemory(
                content=str(entry.get("content", "")),
                event_type=_entry_str(entry, "event_type") or "legacy_team_memory",
                related_entities=_entry_str_list(entry, "related_entities"),
                source_chat_id=_entry_str(entry, "source_chat_id"),
                source_message_id=_entry_str(entry, "source_message_id"),
                importance=_entry_float(entry, "importance", 0.5),
                metadata=_clean_legacy_metadata(entry),
            )
        )

    imported_semantic = await shared_manager.store_batch(semantic_memories)
    imported_episodic = await shared_manager.store_batch(episodic_memories)

    return LegacyTeamMemoryMigrationResponse(
        context=context_to_item(context),
        semantic_imported=len(imported_semantic),
        episodic_imported=len(imported_episodic),
        skipped=skipped,
    )
