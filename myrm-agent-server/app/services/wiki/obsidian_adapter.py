"""Obsidian Vault adapter for Wiki import.

[INPUT]
myrm_agent_harness.agent.meta_tools.file_ops.utils.markdown_frontmatter::parse_frontmatter (POS: YAML FM parse SSOT)
myrm_agent_harness.toolkits.wiki.core.frontmatter_contract::infer_type_for_import, serialize_frontmatter (POS: wiki page type gate SSOT)

[OUTPUT]
- adapt_obsidian_file: Transforms Obsidian-specific syntax and writes raw notes with valid frontmatter `type`.
- rewrite_image_embeds: Rewrites Obsidian image embeds to standard Markdown.
- parse_frontmatter: Re-exported harness SSOT parser for tests and callers.

[POS]
Business-layer adapter that pre-processes Obsidian Vault files for compatibility with the
harness Wiki pipeline. Uses harness SSOT for YAML frontmatter parsing, embedded image references
(![[img]]), .canvas JSON text extraction, and content normalization. Delegates actual import
to the existing scan_folder + WikiCompiler flow.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from myrm_agent_harness.agent.meta_tools.file_ops.utils.markdown_frontmatter import (
    parse_frontmatter,
)
from myrm_agent_harness.toolkits.wiki.core.frontmatter_contract import (
    infer_type_for_import,
    serialize_frontmatter,
)

logger = logging.getLogger(__name__)

_EMBED_IMAGE_RE = re.compile(r"!\[\[([^\]]+\.(?:png|jpg|jpeg|gif|svg|webp|bmp|avif))\]\]", re.IGNORECASE)
_CANVAS_EXT = ".canvas"


@dataclass
class ObsidianImportStats:
    """Aggregated statistics from an Obsidian Vault import."""

    files_scanned: int = 0
    files_processed: int = 0
    files_skipped: int = 0
    tags_extracted: int = 0
    images_copied: int = 0
    frontmatter_parsed: int = 0
    errors: list[str] = field(default_factory=list)


def rewrite_image_embeds(content: str, source_file: Path, vault_root: Path, assets_dest: Path) -> tuple[str, int]:
    """Replace ![[image.png]] embeds with standard Markdown and copy images."""
    copied = 0

    def _replace(m: re.Match[str]) -> str:
        nonlocal copied
        img_name = m.group(1).strip()
        img_source = _find_image(img_name, source_file.parent, vault_root)
        if img_source and img_source.exists():
            dest = assets_dest / img_source.name
            if not dest.exists():
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(img_source, dest)
            copied += 1
            return f"![{img_source.stem}]({img_source.name})"
        return m.group(0)

    result = _EMBED_IMAGE_RE.sub(_replace, content)
    return result, copied


def _find_image(name: str, current_dir: Path, vault_root: Path) -> Path | None:
    """Search for an image file: first in current dir, then recursively in vault."""
    candidate = current_dir / name
    if candidate.exists():
        return candidate
    for found in vault_root.rglob(name):
        if found.is_file():
            return found
    return None


def adapt_obsidian_file(
    source_file: Path,
    vault_root: Path,
    raw_dest_dir: Path,
    assets_dest: Path,
) -> tuple[Path | None, dict[str, object], int]:
    """Process a single Obsidian file and write adapted content to raw_dest_dir.

    Returns (dest_path_or_None, frontmatter_dict, images_copied).
    """
    if source_file.suffix.lower() == _CANVAS_EXT:
        return _adapt_canvas_file(source_file, vault_root, raw_dest_dir)

    try:
        content = source_file.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            content = source_file.read_text(encoding="latin-1")
        except Exception:
            return None, {}, 0

    metadata, body = parse_frontmatter(content)
    body, images_copied = rewrite_image_embeds(body, source_file, vault_root, assets_dest)

    rel_path = source_file.relative_to(vault_root)
    dest_path = raw_dest_dir / rel_path
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    page_type = infer_type_for_import(rel_path, metadata, is_raw_import=True)
    metadata["type"] = page_type.value
    if "sources" not in metadata:
        metadata["sources"] = [str(rel_path).replace("\\", "/")]
    if "provenance" not in metadata:
        metadata["provenance"] = "obsidian_import"

    final_content = serialize_frontmatter(metadata) + body.lstrip("\n")
    dest_path.write_text(final_content, encoding="utf-8")

    return dest_path, metadata, images_copied


def _adapt_canvas_file(
    source_file: Path,
    vault_root: Path,
    raw_dest_dir: Path,
) -> tuple[Path | None, dict[str, object], int]:
    """Extract text content from a JSON Canvas (.canvas) file into a Markdown document.

    Follows JSON Canvas 1.0 spec: nodes[].type=="text" → text content.
    Also extracts node labels for "file" and "link" types.
    """
    try:
        raw = source_file.read_text(encoding="utf-8")
        canvas_data = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        return None, {}, 0

    nodes = canvas_data.get("nodes", [])
    if not nodes:
        return None, {}, 0

    sections: list[str] = []
    for node in nodes:
        node_type = node.get("type", "")
        text = node.get("text", "").strip()
        label = node.get("label", "").strip()

        if node_type == "text" and text:
            sections.append(text)
        elif node_type == "file":
            file_ref = node.get("file", "")
            entry = label or file_ref
            if entry:
                sections.append(f"- File: {entry}")
        elif node_type == "link":
            url = node.get("url", "")
            entry = label or url
            if entry:
                sections.append(f"- Link: {entry}")
        elif node_type == "group" and label:
            sections.append(f"## {label}")

    if not sections:
        return None, {}, 0

    body = "\n\n".join(sections)
    metadata: dict[str, object] = {"source_type": "canvas"}

    rel_path = source_file.relative_to(vault_root).with_suffix(".md")
    dest_path = raw_dest_dir / rel_path
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    page_type = infer_type_for_import(rel_path, metadata, is_raw_import=True)
    metadata["type"] = page_type.value
    metadata["sources"] = [str(rel_path).replace("\\", "/")]
    metadata["provenance"] = "obsidian_canvas_import"
    final_content = serialize_frontmatter(metadata) + body.lstrip("\n")
    dest_path.write_text(final_content, encoding="utf-8")

    return dest_path, metadata, 0
