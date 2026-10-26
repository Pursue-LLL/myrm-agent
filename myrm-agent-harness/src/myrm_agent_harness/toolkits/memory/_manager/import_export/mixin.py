"""MemoryManager mixin: bulk export (JSON, Markdown, privacy-safe rules) and import.

[INPUT]
- memory._manager.host::MemoryManagerHost (POS: typed declaration of the shared manager state)
- memory._manager.shared::iter_pages_by_type (POS: page-by-page walk of one memory type)
- memory._manager.import_export.markdown_render (POS: Markdown and privacy-safe rendering)
- memory.types::{AnyMemory, ConversationMemory, EpisodicMemory, MemoryType, ProceduralMemory, SemanticMemory} (POS: memory data models)

[OUTPUT]
- MemoryManagerImportExportMixin: export_all, export_markdown, export_rules_safe, import_memories

[POS]
Store-facing half of the import/export mixin. ``export_all`` walks every type to its last page and raises
on a store failure, so a backup or export never passes off a truncated result as complete.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

from myrm_agent_harness.toolkits.memory._manager.host import MemoryManagerHost
from myrm_agent_harness.toolkits.memory._manager.import_export.markdown_render import (
    _PERSONAL_FIELDS_TO_STRIP,
    _memory_to_markdown,
    _sanitize_filename,
    sanitize_paths_for_sharing,
)
from myrm_agent_harness.toolkits.memory._manager.shared import (
    iter_pages_by_type,
    logger,
)
from myrm_agent_harness.toolkits.memory.types import (
    AnyMemory,
    ConversationMemory,
    EpisodicMemory,
    MemoryType,
    ProceduralMemory,
    SemanticMemory,
)

# Rows per store round trip while exporting; every page carries its vectors, so this bounds the working set.
_EXPORT_PAGE_SIZE = 2000


class MemoryManagerImportExportMixin(MemoryManagerHost):
    # ── Export / Import ──

    async def export_markdown(
        self,
        target_dir: str | Path,
        *,
        since_ts: datetime | None = None,
        memory_types: list[MemoryType] | None = None,
    ) -> dict[str, int]:
        """Export memories as Markdown files organized by type.

        Each memory becomes a `.md` file with type-specific YAML frontmatter
        inside a subdirectory named after the memory type.

        Args:
            target_dir: Root directory for exported files.
            since_ts: Only export memories created/updated after this timestamp.
            memory_types: Only export these memory types. None = all types.

        Returns:
            Dict with export counts per memory type.
        """
        target = Path(target_dir)
        counts: dict[str, int] = {}

        data = await (self._export_types(memory_types) if memory_types else self.export_all())

        for type_name, entries in data.items():
            type_dir = target / type_name
            type_dir.mkdir(parents=True, exist_ok=True)

            exported = 0
            id_to_path: dict[str, Path] = {}

            for existing_file in type_dir.glob("*.md"):
                try:
                    text = existing_file.read_text(encoding="utf-8")
                    id_match = re.search(r"^id:\s*(.+)$", text, re.MULTILINE)
                    if id_match:
                        id_to_path[id_match.group(1).strip()] = existing_file
                except OSError:
                    pass

            for entry in entries:
                mem_id = str(entry.get("id", ""))

                if since_ts:
                    updated = entry.get("updated_at") or entry.get("created_at")
                    if updated and isinstance(updated, str):
                        try:
                            entry_ts = datetime.fromisoformat(updated)
                            if entry_ts < since_ts:
                                continue
                        except (ValueError, TypeError):
                            pass

                content = str(entry.get("content", ""))
                md_content = _memory_to_markdown(entry, type_name)

                if mem_id in id_to_path:
                    try:
                        id_to_path[mem_id].write_text(md_content, encoding="utf-8")
                        exported += 1
                    except OSError:
                        pass
                else:
                    filename = f"{_sanitize_filename(content)}_{mem_id[:8]}.md"
                    file_path = type_dir / filename
                    file_path.write_text(md_content, encoding="utf-8")
                    id_to_path[mem_id] = file_path
                    exported += 1

            counts[type_name] = exported

        return counts

    async def export_rules_safe(
        self,
        *,
        rule_ids: list[str] | None = None,
        output_format: str = "markdown",
    ) -> list[dict[str, object]]:
        """Export ProceduralMemory rules with privacy sanitization for safe sharing.

        Applies path anonymization and credential redaction, strips personal
        metadata fields (access_count, user_rating, source_chat_id).

        Args:
            rule_ids: Only export these specific rule IDs. None = all rules.
            output_format: "markdown" or "json".

        Returns:
            List of sanitized rule dicts (each with "id", "content", and
            "rendered" key containing the final markdown/json string).
        """
        from myrm_agent_harness.core.security.redact import redact_sensitive_text

        results: list[dict[str, object]] = []
        for entry in await self._export_type(MemoryType.PROCEDURAL):
            mem_id = str(entry.get("id", ""))

            if rule_ids and mem_id not in rule_ids:
                continue

            sanitized = {k: v for k, v in entry.items() if k not in _PERSONAL_FIELDS_TO_STRIP and k != "embedding"}

            for field in ("content", "trigger", "action", "reasoning", "application"):
                val = sanitized.get(field)
                if isinstance(val, str) and val:
                    sanitized[field] = sanitize_paths_for_sharing(redact_sensitive_text(val))

            if output_format == "json":
                rendered = json.dumps(sanitized, ensure_ascii=False, indent=2)
            else:
                rendered = _memory_to_markdown(sanitized, "procedural")

            results.append(
                {
                    "id": mem_id,
                    "content": str(sanitized.get("content", "")),
                    "rendered": rendered,
                }
            )

        return results

    async def _export_type(self, mem_type: MemoryType) -> list[dict[str, object]]:
        """Serialize every stored memory of one type (embeddings excluded); a store error propagates."""
        rows: list[dict[str, object]] = []
        async for page in iter_pages_by_type(
            mem_type,
            page_size=_EXPORT_PAGE_SIZE,
            relational=self._relational,
            vector=self._vector,
            config=self._config,
            namespaces=self._namespaces,
            include_archived=True,
        ):
            rows.extend(m.model_dump(mode="json", exclude={"embedding"}) for m in page)
        return rows

    async def export_all(self) -> dict[str, list[dict[str, object]]]:
        """Export all memories as serializable dicts (excludes embeddings for portability).

        Every type is walked to its last page, and a store failure raises: a backup or an
        export must never pass off a truncated result as a complete one.

        Returns:
            Dict keyed by memory type with lists of serialized memory objects.
        """
        return await self._export_types(MemoryType)

    async def _export_types(self, mem_types: Iterable[MemoryType]) -> dict[str, list[dict[str, object]]]:
        """Serialize the given types, leaving out the ones that hold nothing."""
        result: dict[str, list[dict[str, object]]] = {}
        for mem_type in mem_types:
            if rows := await self._export_type(mem_type):
                result[mem_type.value] = rows
        return result

    async def import_memories(
        self, data: dict[str, list[dict[str, object]]], *, skip_duplicates: bool = True
    ) -> dict[str, int]:
        """Import memories from exported data, recomputing embeddings and routing per type.

        Args:
            data: Dict keyed by memory type with lists of serialized memory objects.
            skip_duplicates: When True (default), deduplicator filters duplicates.

        Returns:
            Dict with import counts per memory type.
        """
        counts: dict[str, int] = {}

        # Only the types the writer stores: claims are compiled from the claim graph, never written back.
        type_parsers: dict[str, type[AnyMemory]] = {
            MemoryType.SEMANTIC.value: SemanticMemory,
            MemoryType.EPISODIC.value: EpisodicMemory,
            MemoryType.PROCEDURAL.value: ProceduralMemory,
            MemoryType.CONVERSATION.value: ConversationMemory,
        }

        saved_dedup = self._deduplicator
        if not skip_duplicates:
            self._deduplicator = None

        try:
            for type_name, entries in data.items():
                parser = type_parsers.get(type_name)
                if parser is None:
                    if type_name == MemoryType.PROFILE.value and self._relational:
                        imported = 0
                        for entry in entries:
                            try:
                                raw_meta = entry.get("metadata")
                                meta = raw_meta if isinstance(raw_meta, dict) else {}
                                key = str(entry.get("key", "") or meta.get("key", ""))
                                value = entry.get("value", "") or meta.get("value", "")
                                if key:
                                    await self._relational.set_profile(key, str(value), scope=self._scope)
                                    imported += 1
                            except Exception as e:
                                logger.warning("Import profile entry failed: %s", e)
                        counts[type_name] = imported
                    continue

                memories: list[AnyMemory] = []
                for entry in entries:
                    try:
                        clean = {k: v for k, v in entry.items() if k not in ("id", "embedding")}
                        mem = parser.model_validate(clean)
                        memories.append(mem)
                    except Exception as e:
                        logger.warning("Import parse failed for %s entry: %s", type_name, e)

                if not memories:
                    counts[type_name] = 0
                    continue

                try:
                    stored = await self.store_batch(memories)
                    counts[type_name] = len(stored)
                except Exception as e:
                    logger.warning("Import batch store failed for %s: %s", type_name, e)
                    counts[type_name] = 0
        finally:
            self._deduplicator = saved_dedup

        return counts
