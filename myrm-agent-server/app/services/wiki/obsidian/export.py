"""Obsidian vault export presets for Settings portability download.

[INPUT]
myrm_agent_harness.toolkits.wiki.portability::build_vault_archive_zip
myrm_agent_harness.toolkits.wiki.core.frontmatter_contract::WikiPageType

[OUTPUT]
build_obsidian_vault_zip: Full vault ZIP with .obsidian/graph.json + README

[POS]
Server-side Obsidian integration (symmetric to obsidian.adapter import).
"""

from __future__ import annotations

import io
import json

from myrm_agent_harness.toolkits.wiki.core.frontmatter_contract import WikiPageType
from myrm_agent_harness.toolkits.wiki.core.structure import WikiStructure
from myrm_agent_harness.toolkits.wiki.portability import build_vault_archive_zip

_README_OBSIDIAN = """Myrm Wiki — Obsidian Vault Pack
================================

1. Unzip this archive to a folder on your computer.
2. In Obsidian: File → Open folder as vault → select the unzipped folder.
3. Open Graph view — page colors follow frontmatter `type` (concept, comparison, source, …).

The `raw/` folder holds imported sources; `wiki/concepts/` holds compiled pages.
Re-download after compile to refresh the snapshot.
"""

_GRAPH_TYPE_COLORS: tuple[tuple[WikiPageType, int], ...] = (
    (WikiPageType.COMPARISON, 0x9333EA),
    (WikiPageType.QUESTION, 0xF59E0B),
    (WikiPageType.ENTITY, 0x059669),
    (WikiPageType.SOURCE, 0x64748B),
    (WikiPageType.SESSION, 0x6366F1),
    (WikiPageType.OVERVIEW, 0x0EA5E9),
    (WikiPageType.CONCEPT, 0x2563EB),
)


def build_obsidian_graph_json() -> dict[str, object]:
    """Build Obsidian graph view preset using frontmatter type queries."""
    color_groups: list[dict[str, object]] = []
    for page_type, rgb in _GRAPH_TYPE_COLORS:
        color_groups.append(
            {
                "query": f"[type:{page_type.value}]",
                "color": {"a": 1, "rgb": rgb},
            }
        )
    return {
        "search": '-path:"wiki/index" -path:"wiki/log" -path:"wiki/hot" -path:"wiki/purpose.md"',
        "hideUnresolved": True,
        "showOrphans": True,
        "collapse-color-groups": False,
        "colorGroups": color_groups,
        "collapse-display": True,
        "showArrow": False,
        "nodeSizeMultiplier": 1,
        "lineSizeMultiplier": 1,
    }


def build_obsidian_vault_zip(structure: WikiStructure, agent_id: str | None = None) -> io.BytesIO:
    """Build a full vault ZIP with Obsidian graph preset and README."""
    graph_json = json.dumps(build_obsidian_graph_json(), indent=2, ensure_ascii=False)
    extra_entries: dict[str, str | bytes] = {
        ".obsidian/graph.json": graph_json,
        "README-OBSIDIAN.txt": _README_OBSIDIAN,
    }
    return build_vault_archive_zip(structure, agent_id, extra_entries=extra_entries)
