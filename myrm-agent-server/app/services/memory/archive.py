"""Single-sandbox memory archive service.

[INPUT]
myrm_agent_harness.toolkits.memory::MemoryArchivePayload (POS: Framework memory reliability kit)
app.database.models.memory::* (POS: 记忆域 ORM 模型)
app.database.models.chat::* (POS: 会话与消息域模型)
app.database.models.agent_event::* (POS: Agent 事件域模型)

[OUTPUT]
MemoryArchiveService: export and dry-run validation for GUI-reviewed memory archives.

[POS]
单用户记忆归档服务。聚合普通记忆、Shared Context、会话、回放事件和审计账本，
生成可审查的本地 archive payload，不包含多租户或控制平面语义。
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

from myrm_agent_harness.toolkits.memory import (
    MemoryArchiveDryRunResult,
    MemoryArchiveManifest,
    MemoryArchivePayload,
    MemoryArchiveSection,
    MemoryArchiveSectionName,
    MemoryManager,
)
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database.models.agent_event import AgentTurn
from app.database.models.chat import Chat
from app.database.models.memory import (
    MemoryOperationEventModel,
    SharedContextBindingModel,
    SharedContextModel,
    SharedContextWriteProposalModel,
)

_PRIVATE_KEY_RE = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
    re.DOTALL,
)
_TOKEN_RE = re.compile(r"\b(?:sk-[A-Za-z0-9_-]{16,}|ghp_[A-Za-z0-9_]{16,}|xox[baprs]-[A-Za-z0-9-]{16,})\b")
_ASSIGNMENT_SECRET_RE = re.compile(r"(?i)\b(api[_-]?key|secret|token|password)\s*[:=]\s*['\"]?[^'\"\s,;]{8,}")


class MemoryArchiveService:
    """Builds content-redacted archive payloads for the current single-user service."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._redaction_count = 0

    async def export_archive(self, manager: MemoryManager) -> MemoryArchivePayload:
        """Export the single-user memory surface into a portable archive payload."""

        self._redaction_count = 0
        memory = self._redact(await self._export_memory(manager))
        shared_context = self._redact(await self._export_shared_context())
        conversation = self._redact(await self._export_conversation())
        replay = self._redact(await self._export_replay())
        audit = self._redact(await self._export_audit())
        data = {
            "memory": memory,
            "shared_context": shared_context,
            "conversation": conversation,
            "replay": replay,
            "audit": audit,
        }
        sections = [
            self._section("memory", memory),
            self._section("shared_context", shared_context),
            self._section("conversation", conversation),
            self._section("replay", replay),
            self._section("audit", audit),
        ]
        return MemoryArchivePayload(
            manifest=MemoryArchiveManifest(
                created_at=datetime.now(UTC).isoformat(),
                sections=sections,
                content_redacted=self._redaction_count > 0,
            ),
            data=data,
        )

    @staticmethod
    def dry_run_archive(payload: dict[str, object]) -> MemoryArchiveDryRunResult:
        """Validate archive shape without mutating server state."""

        archive = MemoryArchivePayload.model_validate(payload)
        supported_names: set[str] = {"memory", "shared_context", "conversation", "replay", "audit"}
        total_items = sum(section.item_count for section in archive.manifest.sections)
        supported_items = sum(section.item_count for section in archive.manifest.sections if section.name in supported_names)
        warning_codes = [code for section in archive.manifest.sections for code in section.warning_codes]
        unsupported_items = total_items - supported_items
        return MemoryArchiveDryRunResult(
            manifest=archive.manifest,
            total_items=total_items,
            supported_items=supported_items,
            unsupported_items=unsupported_items,
            warning_codes=warning_codes,
        )

    async def _export_memory(self, manager: MemoryManager) -> dict[str, list[dict[str, object]]]:
        raw_export = await manager.export_all()
        if not isinstance(raw_export, dict):
            return {}
        exported: dict[str, list[dict[str, object]]] = {}
        for raw_bucket, raw_entries in raw_export.items():
            bucket = str(raw_bucket)
            if not isinstance(raw_entries, list):
                exported[bucket] = []
                continue
            exported[bucket] = [
                {str(key): self._jsonable(value) for key, value in entry.items()}
                for entry in raw_entries
                if isinstance(entry, dict)
            ]
        return exported

    async def _export_shared_context(self) -> dict[str, object]:
        contexts = list((await self._db.execute(select(SharedContextModel))).scalars().all())
        bindings = list((await self._db.execute(select(SharedContextBindingModel))).scalars().all())
        proposals = list((await self._db.execute(select(SharedContextWriteProposalModel))).scalars().all())
        return {
            "contexts": [
                {
                    "id": row.id,
                    "namespace": row.namespace,
                    "name": row.name,
                    "description": row.description,
                    "status": row.status,
                    "policy": row.policy,
                    "created_at": self._jsonable(row.created_at),
                    "updated_at": self._jsonable(row.updated_at),
                }
                for row in contexts
            ],
            "bindings": [
                {
                    "id": row.id,
                    "context_id": row.context_id,
                    "target_type": row.target_type,
                    "target_id": row.target_id,
                    "created_at": self._jsonable(row.created_at),
                }
                for row in bindings
            ],
            "proposals": [
                {
                    "id": row.id,
                    "context_id": row.context_id,
                    "memory_type": row.memory_type,
                    "content": row.content,
                    "metadata": row.metadata_json or {},
                    "source_type": row.source_type,
                    "source_id": row.source_id,
                    "status": row.status,
                    "created_at": self._jsonable(row.created_at),
                    "resolved_at": self._jsonable(row.resolved_at),
                }
                for row in proposals
            ],
        }

    async def _export_conversation(self) -> list[dict[str, object]]:
        result = await self._db.execute(select(Chat).options(selectinload(Chat.messages)).order_by(desc(Chat.updated_at)))
        chats = list(result.scalars().unique().all())
        return [
            {
                "id": chat.id,
                "agent_id": chat.agent_id,
                "title": chat.title,
                "source": chat.source,
                "channel_session_key": chat.channel_session_key,
                "compacted_summary": chat.compacted_summary,
                "compacted_before_id": chat.compacted_before_id,
                "compacted_at": self._jsonable(chat.compacted_at),
                "session_notes_json": chat.session_notes_json,
                "workspace_dir": chat.workspace_dir,
                "created_at": self._jsonable(chat.created_at),
                "updated_at": self._jsonable(chat.updated_at),
                "messages": [
                    {
                        "id": message.id,
                        "role": message.role,
                        "content": message.content,
                        "sent_at": self._jsonable(message.sent_at),
                        "sent_timezone": message.sent_timezone,
                        "extra_data": message.extra_data or {},
                        "is_active": message.is_active,
                    }
                    for message in chat.messages
                ],
            }
            for chat in chats
        ]

    async def _export_replay(self) -> list[dict[str, object]]:
        result = await self._db.execute(
            select(AgentTurn).options(selectinload(AgentTurn.events)).order_by(desc(AgentTurn.created_at))
        )
        turns = list(result.scalars().unique().all())
        return [
            {
                "id": turn.id,
                "chat_id": turn.chat_id,
                "turn_index": turn.turn_index,
                "status": turn.status,
                "event_count": turn.event_count,
                "tool_call_count": turn.tool_call_count,
                "error_count": turn.error_count,
                "duration_ms": turn.duration_ms,
                "created_at": self._jsonable(turn.created_at),
                "started_at": self._jsonable(turn.started_at),
                "completed_at": self._jsonable(turn.completed_at),
                "events": [
                    {
                        "id": event.id,
                        "event_type": event.event_type,
                        "level": event.level,
                        "event_index": event.event_index,
                        "payload": event.payload,
                        "tool_name": event.tool_name,
                        "file_path": event.file_path,
                        "duration_ms": event.duration_ms,
                        "created_at": self._jsonable(event.created_at),
                    }
                    for event in turn.events
                ],
            }
            for turn in turns
        ]

    async def _export_audit(self) -> list[dict[str, object]]:
        result = await self._db.execute(select(MemoryOperationEventModel).order_by(desc(MemoryOperationEventModel.occurred_at)))
        rows = list(result.scalars().all())
        return [
            {
                "id": row.id,
                "kind": row.kind,
                "status": row.status,
                "occurred_at": self._jsonable(row.occurred_at),
                "memory_id": row.memory_id,
                "memory_type": row.memory_type,
                "namespace": row.namespace,
                "source": row.source,
                "summary": row.summary,
                "target_kind": row.target_kind,
                "target_id": row.target_id,
                "correlation_id": row.correlation_id,
                "influence_refs": row.influence_refs_json or [],
                "metadata": row.metadata_json or {},
            }
            for row in rows
        ]

    def _section(self, name: MemoryArchiveSectionName, value: object) -> MemoryArchiveSection:
        item_count = self._count_items(value)
        return MemoryArchiveSection(
            name=name,
            status="ready" if item_count > 0 else "empty",
            item_count=item_count,
        )

    def _count_items(self, value: object) -> int:
        if isinstance(value, list):
            return len(value)
        if isinstance(value, dict):
            return sum(self._count_items(item) for item in value.values())
        return 0

    def _jsonable(self, value: object) -> object:
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, dict):
            return {str(key): self._jsonable(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._jsonable(item) for item in value]
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        return str(value)

    def _redact(self, value: object) -> object:
        if isinstance(value, str):
            redacted = _PRIVATE_KEY_RE.sub("[REDACTED_PRIVATE_KEY]", value)
            redacted = _TOKEN_RE.sub("[REDACTED_TOKEN]", redacted)
            redacted = _ASSIGNMENT_SECRET_RE.sub(lambda match: f"{match.group(1)}=[REDACTED]", redacted)
            if redacted != value:
                self._redaction_count += 1
            return redacted
        if isinstance(value, dict):
            return {str(key): self._redact(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._redact(item) for item in value]
        return value
