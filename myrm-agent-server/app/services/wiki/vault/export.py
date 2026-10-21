"""Wiki vault export for portable Obsidian backup.

[INPUT]
myrm_agent_harness.toolkits.wiki.core.structure::WikiStructure

[OUTPUT]
build_wiki_export_zip: Full vault ZIP with Obsidian graph preset and README

[POS]
Server-side wiki vault export packager for Settings portability download.
"""

from __future__ import annotations

import io

from myrm_agent_harness.toolkits.wiki.core.structure import WikiStructure

from app.services.wiki.obsidian.export import build_obsidian_vault_zip


def build_wiki_export_zip(structure: WikiStructure, agent_id: str | None = None) -> io.BytesIO:
    """Build an Obsidian-ready portable zip of the full agent wiki vault."""
    return build_obsidian_vault_zip(structure, agent_id)
