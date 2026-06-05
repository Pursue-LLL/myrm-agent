"""Memory Archive restore dry-run planner.

[INPUT]
myrm_agent_harness.toolkits.memory::MemoryArchivePayload (POS: framework archive DTOs)
app.database.models.memory::* (POS: 记忆域 ORM 模型)

[OUTPUT]
MemoryArchiveRestoreDryRunResult with section-level safe-merge plan.

[POS]
归档恢复预检层。只读取当前数据库和归档 manifest/data，不写入业务状态。
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass

from myrm_agent_harness.toolkits.memory import (
    MemoryArchivePayload,
    MemoryArchiveRestoreDryRunResult,
    MemoryArchiveRestorePlan,
    MemoryArchiveRestoreSectionPlan,
    MemoryArchiveRestoreSecurityFinding,
    MemoryArchiveRestoreSecurityVerdict,
    MemoryArchiveRestoreStatus,
    MemoryArchiveSectionName,
)
from myrm_agent_harness.toolkits.memory.security import ScanResult, ScanVerdict, scan_memory_content
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import InstrumentedAttribute

from app.database.models.agent_event import AgentTurn
from app.database.models.chat import Chat
from app.database.models.memory import (
    MemoryOperationEventModel,
    SharedContextBindingModel,
    SharedContextModel,
    SharedContextWriteProposalModel,
)
from app.services.memory.archive_restore_common import (
    DEFAULT_ARCHIVE_RESTORE_SECTIONS,
    count_items,
    object_dict,
    object_rows,
    selected_sections,
)
from app.services.memory.import_adapters import build_memory_import_dry_run
from app.services.memory.import_session_data import canonical_hash

MAX_SECURITY_FINDINGS = 100
_BLOCKING_SECURITY_VERDICTS = {"blocked", "redacted"}
_SCAN_SKIPPED_KEYS = {
    "id",
    "chat_id",
    "turn_id",
    "context_id",
    "agent_id",
    "source_id",
    "target_id",
    "correlation_id",
    "thread_id",
    "namespace",
    "status",
    "role",
    "kind",
    "type",
}


@dataclass(frozen=True, slots=True)
class _ArchiveRestoreScanTarget:
    section: MemoryArchiveSectionName
    item_kind: str
    source_id: str
    text: str


class MemoryArchiveRestorePlanner:
    """Builds content-safe archive restore plans."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def dry_run_restore(
        self,
        payload: dict[str, object],
        *,
        sections: Sequence[MemoryArchiveSectionName] | None = None,
    ) -> MemoryArchiveRestoreDryRunResult:
        archive = MemoryArchivePayload.model_validate(payload)
        selected = selected_sections(sections)
        payload_hash = canonical_hash(archive.model_dump(mode="json"))
        plans = [
            await self._section_plan(archive=archive, section=section, selected=section in selected)
            for section in DEFAULT_ARCHIVE_RESTORE_SECTIONS
        ]
        security_findings = _scan_archive_restore_security(archive, selected)
        plan = self._build_plan(
            archive=archive,
            sections=plans,
            selected=selected,
            security_findings=security_findings,
        )
        return MemoryArchiveRestoreDryRunResult(manifest=archive.manifest, plan=plan, payload_hash=payload_hash)

    async def _section_plan(
        self,
        *,
        archive: MemoryArchivePayload,
        section: MemoryArchiveSectionName,
        selected: bool,
    ) -> MemoryArchiveRestoreSectionPlan:
        value = archive.data.get(section)
        item_count = count_items(value)
        if not selected:
            return MemoryArchiveRestoreSectionPlan(
                section=section,
                mode="skip",
                item_count=item_count,
                skipped_items=item_count,
                warning_codes=["section_not_selected"] if item_count else [],
            )
        if section == "memory":
            return self._memory_plan(value)
        if section == "shared_context":
            return await self._shared_context_plan(value)
        if section == "conversation":
            return await self._conversation_plan(value)
        if section == "replay":
            return await self._replay_plan(archive, value)
        if section == "audit":
            return await self._audit_plan(value)
        return MemoryArchiveRestoreSectionPlan(section=section, mode="skip", item_count=item_count, skipped_items=item_count)

    def _memory_plan(self, value: object) -> MemoryArchiveRestoreSectionPlan:
        if not isinstance(value, dict):
            return MemoryArchiveRestoreSectionPlan(
                section="memory",
                mode="skip",
                warning_codes=["memory_section_invalid"],
            )
        result = build_memory_import_dry_run({"version": "1", "data": value}, "native_json")
        return MemoryArchiveRestoreSectionPlan(
            section="memory",
            item_count=result.summary.total_items,
            restorable_items=result.summary.mapped_items,
            skipped_items=result.summary.unmapped_items,
            warning_codes=list(result.warnings),
            target_kinds=list(result.normalized_data.keys()),
        )

    async def _shared_context_plan(self, value: object) -> MemoryArchiveRestoreSectionPlan:
        data = object_dict(value)
        contexts = object_rows(data.get("contexts"))
        bindings = object_rows(data.get("bindings"))
        proposals = object_rows(data.get("proposals"))
        context_conflicts = len(await self._existing_ids(SharedContextModel.id, _row_ids(contexts)))
        binding_conflicts = len(await self._existing_ids(SharedContextBindingModel.id, _row_ids(bindings)))
        proposal_conflicts = len(await self._existing_ids(SharedContextWriteProposalModel.id, _row_ids(proposals)))
        conflict_items = context_conflicts + binding_conflicts + proposal_conflicts
        item_count = len(contexts) + len(bindings) + len(proposals)
        return MemoryArchiveRestoreSectionPlan(
            section="shared_context",
            item_count=item_count,
            restorable_items=max(item_count - conflict_items, 0),
            conflict_items=conflict_items,
            warning_codes=["shared_context_conflicts"] if conflict_items else [],
            target_kinds=["contexts", "bindings", "proposals"],
        )

    async def _conversation_plan(self, value: object) -> MemoryArchiveRestoreSectionPlan:
        rows = object_rows(value)
        conflict_items = len(await self._existing_ids(Chat.id, _row_ids(rows)))
        message_count = sum(len(object_rows(row.get("messages"))) for row in rows)
        return MemoryArchiveRestoreSectionPlan(
            section="conversation",
            item_count=len(rows) + message_count,
            restorable_items=max(len(rows) - conflict_items, 0),
            conflict_items=conflict_items,
            warning_codes=["conversation_conflicts"] if conflict_items else [],
            target_kinds=["chats", "messages"],
        )

    async def _replay_plan(self, archive: MemoryArchivePayload, value: object) -> MemoryArchiveRestoreSectionPlan:
        rows = object_rows(value)
        existing = await self._existing_ids(AgentTurn.id, _row_ids(rows))
        existing_chats = await self._existing_ids(Chat.id, [str(row.get("chat_id") or "") for row in rows])
        archive_chat_ids = {str(row.get("id") or "") for row in object_rows(archive.data.get("conversation"))}
        missing_chats = [
            row
            for row in rows
            if str(row.get("chat_id") or "") not in existing_chats and str(row.get("chat_id") or "") not in archive_chat_ids
        ]
        event_count = sum(len(object_rows(row.get("events"))) for row in rows)
        warnings = []
        if existing:
            warnings.append("replay_conflicts")
        if missing_chats:
            warnings.append("replay_missing_chats")
        return MemoryArchiveRestoreSectionPlan(
            section="replay",
            item_count=len(rows) + event_count,
            restorable_items=max(len(rows) - len(existing) - len(missing_chats), 0),
            skipped_items=len(missing_chats),
            conflict_items=len(existing),
            warning_codes=warnings,
            target_kinds=["turns", "events"],
        )

    async def _audit_plan(self, value: object) -> MemoryArchiveRestoreSectionPlan:
        rows = object_rows(value)
        conflict_items = len(await self._existing_ids(MemoryOperationEventModel.id, _row_ids(rows)))
        return MemoryArchiveRestoreSectionPlan(
            section="audit",
            item_count=len(rows),
            restorable_items=max(len(rows) - conflict_items, 0),
            conflict_items=conflict_items,
            warning_codes=["audit_conflicts"] if conflict_items else [],
            target_kinds=["memory_operation_events"],
        )

    def _build_plan(
        self,
        *,
        archive: MemoryArchivePayload,
        sections: list[MemoryArchiveRestoreSectionPlan],
        selected: tuple[MemoryArchiveSectionName, ...],
        security_findings: list[MemoryArchiveRestoreSecurityFinding],
    ) -> MemoryArchiveRestorePlan:
        blocked_by_section = _blocked_findings_by_section(security_findings)
        enriched_sections = [
            section.model_copy(update={"blocked_items": blocked_by_section.get(section.section, 0)}) for section in sections
        ]
        warning_codes = list(dict.fromkeys(code for section in enriched_sections for code in section.warning_codes))
        blocked_items = sum(blocked_by_section.values())
        if blocked_items > 0:
            warning_codes.append("security_preflight_blocked")
        if len(security_findings) >= MAX_SECURITY_FINDINGS:
            warning_codes.append("security_findings_truncated")
        total_items = sum(section.item_count for section in sections)
        restorable_items = sum(section.restorable_items for section in sections)
        status: MemoryArchiveRestoreStatus = (
            "critical"
            if blocked_items > 0 or (restorable_items == 0 and total_items > 0)
            else "warning"
            if warning_codes
            else "ready"
        )
        plan_hash = canonical_hash(
            {
                "version": 1,
                "archive_format": archive.manifest.format,
                "archive_version": archive.manifest.version,
                "created_at": archive.manifest.created_at,
                "selected_sections": list(selected),
                "sections": [section.model_dump(mode="json") for section in enriched_sections],
                "security_findings": [finding.model_dump(mode="json") for finding in security_findings],
            }
        )
        return MemoryArchiveRestorePlan(
            plan_hash=plan_hash,
            status=status,
            total_items=total_items,
            restorable_items=restorable_items,
            skipped_items=sum(section.skipped_items for section in sections),
            conflict_items=sum(section.conflict_items for section in sections),
            blocked_items=blocked_items,
            warning_codes=warning_codes,
            sections=enriched_sections,
            security_findings=security_findings,
        )

    async def _existing_ids(self, id_column: InstrumentedAttribute[str], ids: Iterable[str]) -> set[str]:
        normalized = [item for item in ids if item]
        if not normalized:
            return set()
        result = await self._db.execute(select(id_column).where(id_column.in_(normalized)))
        return {str(item) for item in result.scalars().all()}


def _row_ids(rows: list[dict[str, object]]) -> list[str]:
    return [str(row.get("id") or "") for row in rows]


def _scan_archive_restore_security(
    archive: MemoryArchivePayload,
    selected: tuple[MemoryArchiveSectionName, ...],
) -> list[MemoryArchiveRestoreSecurityFinding]:
    findings: list[MemoryArchiveRestoreSecurityFinding] = []
    for section in selected:
        for target in _iter_scan_targets(section, archive.data.get(section)):
            result = scan_memory_content(target.text)
            if result.verdict == ScanVerdict.CLEAN:
                continue
            findings.append(
                MemoryArchiveRestoreSecurityFinding(
                    section=target.section,
                    item_kind=target.item_kind,
                    source_id=target.source_id,
                    verdict=_finding_verdict(result.verdict),
                    codes=_finding_codes(result),
                )
            )
            if len(findings) >= MAX_SECURITY_FINDINGS:
                return findings
    return findings


def _iter_scan_targets(section: MemoryArchiveSectionName, value: object) -> Iterator[_ArchiveRestoreScanTarget]:
    if section == "memory":
        data = object_dict(value)
        for bucket, raw_entries in data.items():
            for index, row in enumerate(object_rows(raw_entries)):
                source_id = str(row.get("id") or f"{bucket}:{index}")
                yield from _iter_row_scan_targets(section, f"memory.{bucket}", source_id, row)
        return
    if section == "shared_context":
        data = object_dict(value)
        for bucket in ("contexts", "bindings", "proposals"):
            for index, row in enumerate(object_rows(data.get(bucket))):
                source_id = str(row.get("id") or f"{bucket}:{index}")
                yield from _iter_row_scan_targets(section, f"shared_context.{bucket}", source_id, row)
        return
    item_kind = {
        "conversation": "conversation.chat",
        "replay": "replay.turn",
        "audit": "audit.event",
    }.get(section, section)
    for index, row in enumerate(object_rows(value)):
        source_id = str(row.get("id") or f"{section}:{index}")
        yield from _iter_row_scan_targets(section, item_kind, source_id, row)


def _iter_row_scan_targets(
    section: MemoryArchiveSectionName,
    item_kind: str,
    source_id: str,
    row: dict[str, object],
) -> Iterator[_ArchiveRestoreScanTarget]:
    for text in _iter_scan_strings(row):
        yield _ArchiveRestoreScanTarget(section=section, item_kind=item_kind, source_id=source_id, text=text)


def _iter_scan_strings(value: object, *, key: str = "") -> Iterator[str]:
    if isinstance(value, str):
        if key not in _SCAN_SKIPPED_KEYS and value.strip():
            yield value
        return
    if isinstance(value, dict):
        for raw_key, item in value.items():
            yield from _iter_scan_strings(item, key=str(raw_key))
        return
    if isinstance(value, list):
        for item in value:
            yield from _iter_scan_strings(item, key=key)


def _finding_verdict(verdict: ScanVerdict) -> MemoryArchiveRestoreSecurityVerdict:
    if verdict == ScanVerdict.BLOCKED:
        return "blocked"
    if verdict == ScanVerdict.REDACTED:
        return "redacted"
    return "warn"


def _finding_codes(result: ScanResult) -> list[str]:
    codes: list[str] = []
    codes.extend(f"credential:{pattern}" for pattern in result.credential_patterns)
    codes.extend(f"prompt_injection:{pattern}" for pattern in result.injection_patterns)
    if result.had_invisible_unicode:
        codes.append("invisible_unicode")
    return codes or [f"scan:{result.verdict.value}"]


def _blocked_findings_by_section(
    findings: list[MemoryArchiveRestoreSecurityFinding],
) -> dict[MemoryArchiveSectionName, int]:
    blocked: dict[MemoryArchiveSectionName, int] = {}
    for finding in findings:
        if finding.verdict in _BLOCKING_SECURITY_VERDICTS:
            blocked[finding.section] = blocked.get(finding.section, 0) + 1
    return blocked
