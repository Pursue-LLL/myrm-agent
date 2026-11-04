"""Wiki five-layer document listing service.

[INPUT]
- app.services.wiki.vault::resolve_wiki_vault_path
- myrm_agent_harness.toolkits.wiki.core.structure::WikiStructure
- app.services.wiki.layers.schemas

[OUTPUT]
- WikiLayersService, get_layers_service

[POS]
Lists the markdown documents of each wiki layer with frontmatter title and publish status.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from myrm_agent_harness.toolkits.wiki.core.structure import WikiStructure

from app.services.wiki.layers.schemas import WikiLayerItem
from app.services.wiki.vault import resolve_wiki_vault_path


class WikiLayersService:
    """Service listing the documents inside a wiki layer."""

    def __init__(self, workspace_root: Path | None = None) -> None:
        self.workspace_root = workspace_root

    def _get_structure(self, agent_id: str) -> WikiStructure:
        vault_path = resolve_wiki_vault_path(agent_id)
        structure = WikiStructure(base_dir=vault_path)
        structure.ensure_structure()
        return structure

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

        candidate_files = [p for p in target_dir.rglob("*.md") if p.is_file() and not p.name.startswith(".")]
        candidate_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)

        items: list[WikiLayerItem] = []
        for p in candidate_files[:limit]:
            try:
                text = p.read_text(encoding="utf-8")
            except Exception:
                continue

            title = p.stem.replace("-", " ").replace("_", " ").title()
            publish_status = "published"
            body = text
            if text.startswith("---"):
                parts = text.split("---", 2)
                if len(parts) >= 3:
                    for line in parts[1].splitlines():
                        stripped = line.strip()
                        if stripped.startswith("title:"):
                            title = stripped.split(":", 1)[1].strip().strip('"').strip("'")
                        elif stripped.startswith("publish_status:"):
                            publish_status = stripped.split(":", 1)[1].strip()
                    body = parts[2].strip()

            items.append(
                WikiLayerItem(
                    slug=p.stem,
                    title=title,
                    relative_path=str(p.relative_to(structure.base_dir)),
                    publish_status=publish_status,
                    updated_at=datetime.fromtimestamp(p.stat().st_mtime, UTC).isoformat(timespec="seconds"),
                    content_snippet=body[:280].replace("\n", " ").strip(),
                )
            )

        return items


_service_instance: WikiLayersService | None = None


def get_layers_service(workspace_root: Path | None = None) -> WikiLayersService:
    """Get singleton instance of WikiLayersService."""
    global _service_instance
    if _service_instance is None:
        _service_instance = WikiLayersService(workspace_root=workspace_root)
    return _service_instance
