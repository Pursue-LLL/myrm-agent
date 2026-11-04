"""Wiki writeback domain service managing task usage ledgers and layer inspection.

[INPUT]
- app.services.wiki.vault::resolve_wiki_vault_path
- myrm_agent_harness.toolkits.wiki.core.structure::WikiStructure
- app.services.wiki.writeback.schemas

[OUTPUT]
- WikiWritebackService, get_writeback_service

[POS]
Persists task delivery usage ledgers and lists the documents of each wiki layer.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path

from myrm_agent_harness.toolkits.wiki.core.structure import WikiStructure

from app.services.wiki.vault import resolve_wiki_vault_path
from app.services.wiki.writeback.schemas import UsageLedgerRecord, WikiLayerItem

logger = logging.getLogger(__name__)


class WikiWritebackService:
    """Service handling usage ledger persistence and wiki layer document listing."""

    def __init__(self, workspace_root: Path | None = None) -> None:
        self.workspace_root = workspace_root

    def _get_structure(self, agent_id: str) -> WikiStructure:
        vault_path = resolve_wiki_vault_path(agent_id)
        structure = WikiStructure(base_dir=vault_path)
        structure.ensure_structure()
        return structure

    def record_usage_ledger(
        self,
        agent_id: str,
        record: UsageLedgerRecord,
    ) -> Path:
        """Persist a task usage ledger into deliverables/ledgers/."""
        structure = self._get_structure(agent_id)
        ledgers_dir = structure.deliverables_dir / "ledgers"
        ledgers_dir.mkdir(parents=True, exist_ok=True)

        safe_task_id = re.sub(r"[^\w\s-]", "", record.task_id).strip() or "task_unknown"
        target_path = ledgers_dir / f"{safe_task_id}.json"
        tmp_path = target_path.with_suffix(".tmp")

        tmp_path.write_text(
            record.model_dump_json(indent=2),
            encoding="utf-8",
        )
        tmp_path.replace(target_path)
        logger.info(
            "Persisted usage ledger for task %s to %s",
            record.task_id,
            target_path,
        )
        return target_path

    def list_layer_items(
        self,
        agent_id: str,
        layer_key: str,
        limit: int = 30,
    ) -> list[WikiLayerItem]:
        """List markdown documents in the specified wiki layer with frontmatter parsing."""
        structure = self._get_structure(agent_id)
        layer_dir_map: dict[str, Path] = {
            "l1": structure.raw_dir,
            "raw": structure.raw_dir,
            "inbox": structure.inbox_dir,
            "l2": structure.sources_dir,
            "sources": structure.sources_dir,
            "l3": structure.methods_dir,
            "methods": structure.methods_dir,
            "concepts": structure.concepts_dir,
            "l4": structure.claims_dir,
            "claims": structure.claims_dir,
            "l5": structure.deliverables_dir,
            "deliverables": structure.deliverables_dir,
        }
        target_dir = layer_dir_map.get(layer_key.lower())
        if not target_dir or not target_dir.is_dir():
            return []

        items: list[WikiLayerItem] = []
        is_deliverables = layer_key.lower() in ("l5", "deliverables")
        if is_deliverables:
            candidate_files = [
                p
                for p in target_dir.rglob("*")
                if p.is_file()
                and not p.name.startswith(".")
                and p.suffix.lower() in (".md", ".json")
            ]
        else:
            candidate_files = [
                p
                for p in target_dir.rglob("*.md")
                if p.is_file() and not p.name.startswith(".")
            ]

        candidate_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)

        for p in candidate_files[:limit]:
            try:
                text = p.read_text(encoding="utf-8")
            except Exception:
                continue

            file_type = "json" if p.suffix.lower() == ".json" else "markdown"
            title = p.stem.replace("-", " ").replace("_", " ").title()
            publish_status = "published"
            source_task_id: str | None = None

            if file_type == "json":
                try:
                    data = json.loads(text)
                    if isinstance(data, dict):
                        source_task_id = str(data.get("task_id") or "").strip() or None
                        raw_title = data.get("title")
                        if raw_title and isinstance(raw_title, str):
                            title = raw_title.strip()
                        executed_at = data.get("executed_at", "")
                        items_count = len(data.get("items", []))
                        snippet = f"Task: {source_task_id or p.stem} | Entries: {items_count} | Executed: {executed_at}"
                    else:
                        snippet = text[:280].replace("\n", " ").strip()
                except Exception:
                    snippet = text[:280].replace("\n", " ").strip()
            else:
                if text.startswith("---"):
                    parts = text.split("---", 2)
                    if len(parts) >= 3:
                        fm_text = parts[1]
                        for line in fm_text.splitlines():
                            stripped = line.strip()
                            if stripped.startswith("title:"):
                                title = stripped.split(":", 1)[1].strip().strip('"').strip("'")
                            elif stripped.startswith("publish_status:"):
                                publish_status = stripped.split(":", 1)[1].strip()
                            elif stripped.startswith("source_task_id:"):
                                source_task_id = stripped.split(":", 1)[1].strip().strip('"').strip("'")
                        body = parts[2].strip()
                    else:
                        body = text
                else:
                    body = text
                snippet = body[:280].replace("\n", " ").strip()

            mtime_iso = datetime.fromtimestamp(p.stat().st_mtime, UTC).isoformat(timespec="seconds")
            rel_path = str(p.relative_to(structure.base_dir))

            items.append(
                WikiLayerItem(
                    slug=p.stem,
                    title=title,
                    relative_path=rel_path,
                    publish_status=publish_status,
                    updated_at=mtime_iso,
                    content_snippet=snippet,
                    source_task_id=source_task_id,
                    file_type=file_type,
                )
            )

        return items


_service_instance: WikiWritebackService | None = None


def get_writeback_service(workspace_root: Path | None = None) -> WikiWritebackService:
    """Get singleton instance of WikiWritebackService."""
    global _service_instance
    if _service_instance is None:
        _service_instance = WikiWritebackService(workspace_root=workspace_root)
    return _service_instance
