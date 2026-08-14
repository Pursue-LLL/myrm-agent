"""Memory Archive safe-merge restore executor.

[INPUT] MemoryArchivePayload, MemoryManager, selected archive sections (POS: framework archive DTOs)
[OUTPUT] MemoryArchiveRestoreExecutor: writes safe-merge mutations and rollback ledger rows.
[POS] 归档恢复执行层。写入 memory/Shared Context/conversation/replay/audit 分区并记录可回滚账本。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from myrm_agent_harness.toolkits.memory import (
    MemoryArchivePayload,
    MemoryArchiveRestoreItemStatus,
    MemoryArchiveRestoreMutationRef,
    MemoryArchiveSectionName,
    MemoryManager,
    MemoryType,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.agent_event import AgentEvent, AgentTurn
from app.database.models.chat import Chat, Message
from app.database.models.memory import (
    MemoryOperationEventModel,
    SharedContextBindingModel,
    SharedContextModel,
    SharedContextWriteProposalModel,
)
from app.services.memory.archive_restore_common import (
    RESTORE_ITEM_STATUS_RESTORED,
    RESTORE_ITEM_STATUS_SKIPPED,
    add_restore_item,
    int_value,
    make_ref,
    object_dict,
    object_rows,
    optional_int,
    optional_str,
    parse_datetime,
    parse_datetime_or_none,
    refs_by_import_item,
    selected_sections,
)
from app.services.memory.import_adapters import build_memory_import_dry_run
from app.services.memory.import_session_data import (
    attach_import_metadata,
    capture_profile_imported_values,
    capture_profile_previous_values,
    profile_entry_key,
)


class MemoryArchiveRestoreExecutor:
    """Executes selected archive sections and writes rollback ledger items."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def restore_sections(
        self,
        *,
        archive: MemoryArchivePayload,
        batch_id: str,
        payload_hash: str,
        manager: MemoryManager,
        sections: Sequence[MemoryArchiveSectionName] | None,
        skip_duplicates: bool,
    ) -> list[MemoryArchiveRestoreMutationRef]:
        refs: list[MemoryArchiveRestoreMutationRef] = []
        for section in selected_sections(sections):
            refs.extend(
                await self._restore_section(
                    archive=archive,
                    section=section,
                    batch_id=batch_id,
                    payload_hash=payload_hash,
                    manager=manager,
                    skip_duplicates=skip_duplicates,
                )
            )
        return refs

    async def _restore_section(
        self,
        *,
        archive: MemoryArchivePayload,
        section: MemoryArchiveSectionName,
        batch_id: str,
        payload_hash: str,
        manager: MemoryManager,
        skip_duplicates: bool,
    ) -> list[MemoryArchiveRestoreMutationRef]:
        if section == "memory":
            return await self._restore_memory(archive.data.get("memory"), batch_id, payload_hash, manager, skip_duplicates)
        if section == "shared_context":
            return await self._restore_shared_context(archive.data.get("shared_context"), batch_id)
        if section == "conversation":
            return await self._restore_conversation(archive.data.get("conversation"), batch_id)
        if section == "replay":
            return await self._restore_replay(archive.data.get("replay"), batch_id)
        if section == "audit":
            return await self._restore_audit(archive.data.get("audit"), batch_id)
        return []

    async def _restore_memory(
        self,
        value: object,
        batch_id: str,
        payload_hash: str,
        manager: MemoryManager,
        skip_duplicates: bool,
    ) -> list[MemoryArchiveRestoreMutationRef]:
        if not isinstance(value, dict):
            return []
        dry_run = build_memory_import_dry_run({"version": "1", "data": value}, "native_json")
        normalized = dry_run.normalized_data
        previous_profiles = await capture_profile_previous_values(manager, normalized)
        enriched = attach_import_metadata(
            normalized,
            import_batch_id=batch_id,
            source="myrm_archive_restore",
            dry_run_id=batch_id,
            payload_hash=payload_hash,
        )
        for entries in enriched.values():
            for entry in entries:
                metadata = object_dict(entry.get("metadata"))
                metadata["archive_restore_batch_id"] = batch_id
                entry["metadata"] = metadata
        await manager.import_memories(enriched, skip_duplicates=skip_duplicates)
        stored_refs = await manager.list_memory_refs_by_metadata("archive_restore_batch_id", batch_id)
        refs_by_item = refs_by_import_item(stored_refs)
        profile_imported = await capture_profile_imported_values(manager, enriched)
        refs: list[MemoryArchiveRestoreMutationRef] = []
        for bucket, entries in enriched.items():
            for index, entry in enumerate(entries):
                refs.append(
                    self._record_memory_restore_item(
                        batch_id=batch_id,
                        bucket=bucket,
                        index=index,
                        entry=entry,
                        refs_by_item=refs_by_item,
                        previous_profiles=previous_profiles,
                        profile_imported=profile_imported,
                    )
                )
        return refs

    def _record_memory_restore_item(
        self,
        *,
        batch_id: str,
        bucket: str,
        index: int,
        entry: dict[str, object],
        refs_by_item: dict[str, list[str]],
        previous_profiles: Mapping[str, object],
        profile_imported: Mapping[str, object],
    ) -> MemoryArchiveRestoreMutationRef:
        metadata = object_dict(entry.get("metadata"))
        import_item_id = str(metadata.get("import_item_id") or f"{batch_id}:{bucket}:{index}")
        memory_ids = refs_by_item.get(import_item_id, [])
        profile_key = profile_entry_key(entry) if bucket == MemoryType.PROFILE.value else None
        previous = previous_profiles.get(profile_key) if profile_key else None
        imported = profile_imported.get(profile_key) if profile_key else None
        restored = bool(memory_ids or (profile_key and getattr(imported, "exists", False)))
        target_id = profile_key or ",".join(memory_ids)
        ref = make_ref(
            section="memory",
            item_kind=f"memory.{bucket}",
            source_id=import_item_id,
            target_id=target_id,
            status=RESTORE_ITEM_STATUS_RESTORED if restored else RESTORE_ITEM_STATUS_SKIPPED,
            reason="" if restored else "duplicate_or_unstored",
        )
        self._db.add(
            add_restore_item(
                batch_id=batch_id,
                ref=ref,
                metadata={
                    "memory_type": bucket,
                    "memory_ids": memory_ids,
                    "profile_key": profile_key,
                    "profile_previous_value": getattr(previous, "value", None),
                    "profile_previous_present": bool(getattr(previous, "exists", False)),
                    "profile_previous_revision": str(getattr(previous, "revision", "")),
                    "profile_imported_value": getattr(imported, "value", None),
                    "profile_imported_present": bool(getattr(imported, "exists", False)),
                    "profile_imported_revision": str(getattr(imported, "revision", "")),
                },
            )
        )
        return ref

    async def _restore_shared_context(self, value: object, batch_id: str) -> list[MemoryArchiveRestoreMutationRef]:
        data = object_dict(value)
        refs: list[MemoryArchiveRestoreMutationRef] = []
        restored_context_ids: set[str] = set()
        for row in object_rows(data.get("contexts")):
            context_id = str(row.get("id") or "")
            existing_context = await self._shared_context_exists(context_id) if context_id else False
            namespace_exists = await self._namespace_exists(row) if context_id else False
            if not context_id or existing_context or namespace_exists:
                refs.append(
                    self._tracked_ref(batch_id, "shared_context", "shared_context.context", context_id, context_id, "conflict")
                )
                continue
            self._db.add(
                SharedContextModel(
                    id=context_id,
                    namespace=str(row.get("namespace") or f"shared:{context_id}"),
                    name=str(row.get("name") or "Imported Shared Context"),
                    description=str(row.get("description") or ""),
                    status=str(row.get("status") or "active"),
                    policy=object_dict(row.get("policy")),
                    created_at=parse_datetime(row.get("created_at")),
                    updated_at=parse_datetime(row.get("updated_at")),
                )
            )
            restored_context_ids.add(context_id)
            refs.append(
                self._tracked_ref(batch_id, "shared_context", "shared_context.context", context_id, context_id, "restored")
            )
        await self._db.flush()
        refs.extend(await self._restore_shared_bindings(data, batch_id, restored_context_ids))
        refs.extend(await self._restore_shared_proposals(data, batch_id, restored_context_ids))
        await self._db.flush()
        return refs

    async def _restore_shared_bindings(
        self,
        data: dict[str, object],
        batch_id: str,
        restored_context_ids: set[str],
    ) -> list[MemoryArchiveRestoreMutationRef]:
        refs: list[MemoryArchiveRestoreMutationRef] = []
        for row in object_rows(data.get("bindings")):
            binding_id = str(row.get("id") or "")
            context_id = str(row.get("context_id") or "")
            binding_exists = await self._shared_binding_exists(binding_id) if binding_id else False
            if not binding_id or context_id not in restored_context_ids or binding_exists:
                refs.append(
                    self._tracked_ref(batch_id, "shared_context", "shared_context.binding", binding_id, binding_id, "conflict")
                )
                continue
            self._db.add(
                SharedContextBindingModel(
                    id=binding_id,
                    context_id=context_id,
                    target_type=str(row.get("target_type") or "conversation"),
                    target_id=str(row.get("target_id") or ""),
                    created_at=parse_datetime(row.get("created_at")),
                )
            )
            refs.append(
                self._tracked_ref(batch_id, "shared_context", "shared_context.binding", binding_id, binding_id, "restored")
            )
        return refs

    async def _restore_shared_proposals(
        self,
        data: dict[str, object],
        batch_id: str,
        restored_context_ids: set[str],
    ) -> list[MemoryArchiveRestoreMutationRef]:
        refs: list[MemoryArchiveRestoreMutationRef] = []
        for row in object_rows(data.get("proposals")):
            proposal_id = str(row.get("id") or "")
            context_id = str(row.get("context_id") or "")
            proposal_exists = await self._shared_proposal_exists(proposal_id) if proposal_id else False
            if not proposal_id or context_id not in restored_context_ids or proposal_exists:
                refs.append(
                    self._tracked_ref(batch_id, "shared_context", "shared_context.proposal", proposal_id, proposal_id, "conflict")
                )
                continue
            self._db.add(
                SharedContextWriteProposalModel(
                    id=proposal_id,
                    context_id=context_id,
                    memory_type=str(row.get("memory_type") or "semantic"),
                    content=str(row.get("content") or ""),
                    metadata_json=object_dict(row.get("metadata")),
                    source_type=str(row.get("source_type") or "archive_restore"),
                    source_id=optional_str(row.get("source_id")),
                    status=str(row.get("status") or "pending"),
                    created_at=parse_datetime(row.get("created_at")),
                    resolved_at=parse_datetime_or_none(row.get("resolved_at")),
                )
            )
            refs.append(
                self._tracked_ref(batch_id, "shared_context", "shared_context.proposal", proposal_id, proposal_id, "restored")
            )
        return refs

    async def _restore_conversation(self, value: object, batch_id: str) -> list[MemoryArchiveRestoreMutationRef]:
        refs: list[MemoryArchiveRestoreMutationRef] = []
        for row in object_rows(value):
            chat_id = str(row.get("id") or "")
            channel_key = optional_str(row.get("channel_session_key"))
            chat_exists = await self._chat_exists(chat_id) if chat_id else False
            channel_key_exists = await self._channel_key_exists(channel_key) if chat_id else False
            if not chat_id or chat_exists or channel_key_exists:
                refs.append(self._tracked_ref(batch_id, "conversation", "conversation.chat", chat_id, chat_id, "conflict"))
                continue
            messages = object_rows(row.get("messages"))
            self._db.add(_chat_from_archive(row, messages))
            for message in messages:
                message_id = str(message.get("id") or "")
                if message_id:
                    self._db.add(_message_from_archive(message, chat_id))
            refs.append(
                self._tracked_ref(
                    batch_id,
                    "conversation",
                    "conversation.chat",
                    chat_id,
                    chat_id,
                    "restored",
                    metadata={"message_count": len(messages)},
                )
            )
        await self._db.flush()
        return refs

    async def _restore_replay(self, value: object, batch_id: str) -> list[MemoryArchiveRestoreMutationRef]:
        refs: list[MemoryArchiveRestoreMutationRef] = []
        for row in object_rows(value):
            turn_id = str(row.get("id") or "")
            chat_id = str(row.get("chat_id") or "")
            turn_exists = await self._turn_exists(turn_id) if turn_id else False
            if not turn_id or turn_exists:
                refs.append(self._tracked_ref(batch_id, "replay", "replay.turn", turn_id, turn_id, "conflict"))
                continue
            if not chat_id or not await self._chat_exists(chat_id):
                refs.append(self._tracked_ref(batch_id, "replay", "replay.turn", turn_id, turn_id, "skipped", "chat_missing"))
                continue
            events = object_rows(row.get("events"))
            self._db.add(_turn_from_archive(row, events))
            for event in events:
                event_id = str(event.get("id") or "")
                if event_id:
                    self._db.add(_event_from_archive(event, turn_id))
            refs.append(
                self._tracked_ref(
                    batch_id,
                    "replay",
                    "replay.turn",
                    turn_id,
                    turn_id,
                    "restored",
                    metadata={"event_count": len(events)},
                )
            )
        await self._db.flush()
        return refs

    async def _restore_audit(self, value: object, batch_id: str) -> list[MemoryArchiveRestoreMutationRef]:
        refs: list[MemoryArchiveRestoreMutationRef] = []
        for row in object_rows(value):
            event_id = str(row.get("id") or "")
            event_exists = await self._audit_event_exists(event_id) if event_id else False
            if not event_id or event_exists:
                refs.append(self._tracked_ref(batch_id, "audit", "audit.event", event_id, event_id, "conflict"))
                continue
            metadata = object_dict(row.get("metadata")) | {"archive_restored": True, "archive_restore_batch_id": batch_id}
            self._db.add(_audit_from_archive(row, metadata))
            refs.append(self._tracked_ref(batch_id, "audit", "audit.event", event_id, event_id, "restored"))
        await self._db.flush()
        return refs

    async def _namespace_exists(self, row: dict[str, object]) -> bool:
        namespace = optional_str(row.get("namespace"))
        if not namespace:
            return False
        result = await self._db.execute(select(SharedContextModel.id).where(SharedContextModel.namespace == namespace))
        return result.scalar_one_or_none() is not None

    async def _shared_context_exists(self, context_id: str) -> bool:
        result = await self._db.execute(select(SharedContextModel.id).where(SharedContextModel.id == context_id))
        return result.scalar_one_or_none() is not None

    async def _shared_binding_exists(self, binding_id: str) -> bool:
        result = await self._db.execute(select(SharedContextBindingModel.id).where(SharedContextBindingModel.id == binding_id))
        return result.scalar_one_or_none() is not None

    async def _shared_proposal_exists(self, proposal_id: str) -> bool:
        result = await self._db.execute(
            select(SharedContextWriteProposalModel.id).where(SharedContextWriteProposalModel.id == proposal_id)
        )
        return result.scalar_one_or_none() is not None

    async def _chat_exists(self, chat_id: str) -> bool:
        result = await self._db.execute(select(Chat.id).where(Chat.id == chat_id))
        return result.scalar_one_or_none() is not None

    async def _turn_exists(self, turn_id: str) -> bool:
        result = await self._db.execute(select(AgentTurn.id).where(AgentTurn.id == turn_id))
        return result.scalar_one_or_none() is not None

    async def _audit_event_exists(self, event_id: str) -> bool:
        result = await self._db.execute(select(MemoryOperationEventModel.id).where(MemoryOperationEventModel.id == event_id))
        return result.scalar_one_or_none() is not None

    async def _channel_key_exists(self, channel_key: str | None) -> bool:
        if not channel_key:
            return False
        result = await self._db.execute(select(Chat.id).where(Chat.channel_session_key == channel_key))
        return result.scalar_one_or_none() is not None

    def _tracked_ref(
        self,
        batch_id: str,
        section: MemoryArchiveSectionName,
        item_kind: str,
        source_id: str,
        target_id: str,
        status: MemoryArchiveRestoreItemStatus,
        reason: str = "",
        metadata: dict[str, object] | None = None,
    ) -> MemoryArchiveRestoreMutationRef:
        ref = make_ref(
            section=section, item_kind=item_kind, source_id=source_id, target_id=target_id, status=status, reason=reason
        )
        self._db.add(add_restore_item(batch_id=batch_id, ref=ref, metadata=metadata))
        return ref


def _chat_from_archive(row: dict[str, object], messages: list[dict[str, object]]) -> Chat:
    first_message = str(messages[0].get("content") or "") if messages else None
    last_message = str(messages[-1].get("content") or "") if messages else None
    return Chat(
        id=str(row.get("id") or ""),
        agent_id=optional_str(row.get("agent_id")),
        title=optional_str(row.get("title")),
        first_message=first_message,
        last_message=last_message,
        source=str(row.get("source") or "archive_restore"),
        channel_session_key=optional_str(row.get("channel_session_key")),
        compacted_summary=optional_str(row.get("compacted_summary")),
        compacted_before_id=optional_str(row.get("compacted_before_id")),
        compacted_at=parse_datetime_or_none(row.get("compacted_at")),
        session_notes_json=optional_str(row.get("session_notes_json")),
        workspace_dir=optional_str(row.get("workspace_dir")),
        created_at=parse_datetime(row.get("created_at")),
        updated_at=parse_datetime(row.get("updated_at")),
    )


def _message_from_archive(row: dict[str, object], chat_id: str) -> Message:
    return Message(
        id=str(row.get("id") or ""),
        chat_id=chat_id,
        role=str(row.get("role") or "assistant"),
        content=str(row.get("content") or ""),
        sent_at=parse_datetime(row.get("sent_at")),
        sent_timezone=str(row.get("sent_timezone") or "UTC"),
        extra_data=object_dict(row.get("extra_data")),
        is_active=bool(row.get("is_active", True)),
    )


def _turn_from_archive(row: dict[str, object], events: list[dict[str, object]]) -> AgentTurn:
    return AgentTurn(
        id=str(row.get("id") or ""),
        chat_id=str(row.get("chat_id") or ""),
        turn_index=int_value(row.get("turn_index")),
        status=str(row.get("status") or "completed"),
        event_count=int_value(row.get("event_count"), len(events)),
        tool_call_count=int_value(row.get("tool_call_count")),
        error_count=int_value(row.get("error_count")),
        duration_ms=optional_int(row.get("duration_ms")),
        created_at=parse_datetime(row.get("created_at")),
        started_at=parse_datetime_or_none(row.get("started_at")),
        completed_at=parse_datetime_or_none(row.get("completed_at")),
    )


def _event_from_archive(row: dict[str, object], turn_id: str) -> AgentEvent:
    return AgentEvent(
        id=str(row.get("id") or ""),
        turn_id=turn_id,
        event_type=str(row.get("event_type") or "archive_restore"),
        level=str(row.get("level") or "info"),
        event_index=int_value(row.get("event_index")),
        payload=object_dict(row.get("payload")),
        tool_name=optional_str(row.get("tool_name")),
        file_path=optional_str(row.get("file_path")),
        duration_ms=optional_int(row.get("duration_ms")),
        created_at=parse_datetime(row.get("created_at")),
    )


def _audit_from_archive(row: dict[str, object], metadata: dict[str, object]) -> MemoryOperationEventModel:
    return MemoryOperationEventModel(
        id=str(row.get("id") or ""),
        kind=str(row.get("kind") or "observe"),
        status=str(row.get("status") or "success"),
        occurred_at=parse_datetime(row.get("occurred_at")),
        memory_id=optional_str(row.get("memory_id")),
        memory_type=optional_str(row.get("memory_type")),
        namespace=optional_str(row.get("namespace")),
        source=optional_str(row.get("source")),
        summary=str(row.get("summary") or "Restored archive audit event."),
        target_kind=optional_str(row.get("target_kind")),
        target_id=optional_str(row.get("target_id")),
        correlation_id=optional_str(row.get("correlation_id")),
        influence_refs_json=object_rows(row.get("influence_refs")),
        metadata_json=metadata,
    )
