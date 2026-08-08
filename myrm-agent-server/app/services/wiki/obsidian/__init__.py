"""Obsidian domain — Vault import adapter and export presets.

[INPUT]
- app.services.wiki.obsidian.adapter (POS: Obsidian file import transform)
- app.services.wiki.obsidian.export (POS: Obsidian-ready vault ZIP presets)

[OUTPUT]
- prepare_obsidian_file / adapt_obsidian_file / rewrite_image_embeds: import path
- build_obsidian_vault_zip / build_obsidian_graph_json: export path
- parse_frontmatter: re-exported harness SSOT parser

[POS]
Domain subpackage for Obsidian integration. Facade module name
``app.services.wiki.obsidian`` aggregates adapter / export presets.
"""

from __future__ import annotations

from app.services.wiki.obsidian.adapter import (
    ObsidianImportStats,
    ObsidianRawPrepared,
    adapt_obsidian_file,
    extract_inline_obsidian_tags,
    merge_obsidian_tags,
    parse_frontmatter,
    prepare_obsidian_file,
    rewrite_image_embeds,
)
from app.services.wiki.obsidian.export import (
    build_obsidian_graph_json,
    build_obsidian_vault_zip,
)

__all__ = [
    "ObsidianImportStats",
    "ObsidianRawPrepared",
    "adapt_obsidian_file",
    "build_obsidian_graph_json",
    "build_obsidian_vault_zip",
    "extract_inline_obsidian_tags",
    "merge_obsidian_tags",
    "parse_frontmatter",
    "prepare_obsidian_file",
    "rewrite_image_embeds",
]
