"""Obsidian Vault adapter for Wiki import.

[INPUT]
myrm_agent_harness.agent.meta_tools.file_ops.utils.markdown_frontmatter::parse_frontmatter (POS: YAML FM parse SSOT)
myrm_agent_harness.toolkits.wiki.core.frontmatter_contract::infer_type_for_import, serialize_frontmatter (POS: wiki page type gate SSOT)

[OUTPUT]
- prepare_obsidian_file: Transforms Obsidian syntax without writing raw/.
- adapt_obsidian_file: Legacy/test direct write to a raw directory.
- rewrite_image_embeds: Rewrites Obsidian image embeds to standard Markdown.
- parse_frontmatter: Re-exported harness SSOT parser for tests and callers.

[POS]
Business-layer adapter that pre-processes Obsidian Vault files for the harness Wiki pipeline.
Production import routes call prepare_obsidian_file then harness publish_raw; this module does not
bypass the raw publication gate.
"""

from __future__ import annotations

import hashlib
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
_INLINE_TAG_RE = re.compile(r"(?<![\w/`])#([A-Za-z][A-Za-z0-9_/-]*)")
_CANVAS_EXT = ".canvas"


@dataclass(frozen=True, slots=True)
class ObsidianRawPrepared:
    """Adapted Obsidian note ready for raw_gate publication."""

    relative_path: str
    content: str
    metadata: dict[str, object]
    images_copied: int


@dataclass
class ObsidianImportStats:
    """Aggregated statistics from an Obsidian Vault import."""

    files_scanned: int = 0
    files_processed: int = 0
    files_skipped: int = 0
    files_skipped_conflict: int = 0
    files_superseded: int = 0
    tags_extracted: int = 0
    images_copied: int = 0
    frontmatter_parsed: int = 0
    errors: list[str] = field(default_factory=list)


def merge_obsidian_tags(existing: list[str], inline: list[str]) -> list[str]:
    """Merge frontmatter tags with inline tags, preserving first-seen casing."""
    merged: list[str] = list(existing)
    seen = {tag.casefold() for tag in merged}
    for tag in inline:
        key = tag.casefold()
        if key in seen:
            continue
        merged.append(tag)
        seen.add(key)
    return merged


def extract_inline_obsidian_tags(body: str) -> tuple[str, list[str]]:
    """Promote Obsidian inline #tags into frontmatter and strip them from body."""
    if not body:
        return body, []

    parts = body.split("```")
    cleaned_parts: list[str] = []
    tags: list[str] = []

    for index, part in enumerate(parts):
        if index % 2 == 1:
            cleaned_parts.append(part)
            continue

        lines = part.splitlines(keepends=True)
        segment_parts: list[str] = []
        for line in lines:
            stripped = line.lstrip()
            if re.match(r"^#{1,6}\s+\S", stripped):
                segment_parts.append(line)
                continue

            def _replace(match: re.Match[str]) -> str:
                tag = match.group(1)
                if tag not in tags:
                    tags.append(tag)
                return ""

            segment_parts.append(_INLINE_TAG_RE.sub(_replace, line))

        cleaned_parts.append("".join(segment_parts))

    cleaned = "```".join(cleaned_parts)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r" ?\n", "\n", cleaned)
    return cleaned, tags


def rewrite_image_embeds(content: str, source_file: Path, vault_root: Path, assets_dest: Path) -> tuple[str, int]:
    """Replace ![[image.png]] embeds with standard Markdown and copy images."""
    copied = 0

    def _replace(m: re.Match[str]) -> str:
        nonlocal copied
        img_name = m.group(1).strip()
        img_source = _find_image(img_name, source_file.parent, vault_root)
        if img_source and img_source.exists():
            file_hash = hashlib.sha256(img_source.read_bytes()).hexdigest()[:12]
            dest_name = f"{file_hash}_{img_source.name}"
            dest = assets_dest / dest_name
            if not dest.exists():
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(img_source, dest)
            copied += 1
            return f"![{img_source.stem}]({dest_name})"
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


def prepare_obsidian_file(
    source_file: Path,
    vault_root: Path,
    assets_dest: Path,
) -> ObsidianRawPrepared | None:
    """Transform a single Obsidian file without writing to raw/."""
    if source_file.suffix.lower() == _CANVAS_EXT:
        return _prepare_canvas_file(source_file, vault_root)

    try:
        content = source_file.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            content = source_file.read_text(encoding="latin-1")
        except Exception:
            return None

    metadata, body = parse_frontmatter(content)
    body, inline_tags = extract_inline_obsidian_tags(body)
    if inline_tags:
        existing_tags = metadata.get("tags")
        if isinstance(existing_tags, list):
            base_tags = [str(tag) for tag in existing_tags]
        elif existing_tags:
            base_tags = [str(existing_tags)]
        else:
            base_tags = []
        metadata["tags"] = merge_obsidian_tags(base_tags, inline_tags)

    body, images_copied = rewrite_image_embeds(body, source_file, vault_root, assets_dest)

    rel_path = source_file.relative_to(vault_root)
    page_type = infer_type_for_import(rel_path, metadata, is_raw_import=True)
    metadata["type"] = page_type.value
    if "sources" not in metadata:
        metadata["sources"] = [str(rel_path).replace("\\", "/")]
    if "provenance" not in metadata:
        metadata["provenance"] = "obsidian_import"

    final_content = serialize_frontmatter(metadata) + body.lstrip("\n")
    return ObsidianRawPrepared(
        relative_path=str(rel_path).replace("\\", "/"),
        content=final_content,
        metadata=metadata,
        images_copied=images_copied,
    )


def adapt_obsidian_file(
    source_file: Path,
    vault_root: Path,
    raw_dest_dir: Path,
    assets_dest: Path,
) -> tuple[Path | None, dict[str, object], int]:
    """Process a single Obsidian file and write adapted content to raw_dest_dir.

    Returns (dest_path_or_None, frontmatter_dict, images_copied).
    """
    prepared = prepare_obsidian_file(source_file, vault_root, assets_dest)
    if prepared is None:
        return None, {}, 0

    dest_path = raw_dest_dir / prepared.relative_path
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    dest_path.write_text(prepared.content, encoding="utf-8")
    return dest_path, prepared.metadata, prepared.images_copied


def _prepare_canvas_file(
    source_file: Path,
    vault_root: Path,
) -> ObsidianRawPrepared | None:
    """Extract text content from a JSON Canvas (.canvas) file into a Markdown document.

    Follows JSON Canvas 1.0 spec: nodes[].type=="text" → text content.
    Also extracts node labels for "file" and "link" types.
    """
    try:
        raw = source_file.read_text(encoding="utf-8")
        canvas_data = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        return None

    nodes = canvas_data.get("nodes", [])
    if not nodes:
        return None

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
        return None

    body = "\n\n".join(sections)
    metadata: dict[str, object] = {"source_type": "canvas"}

    rel_path = source_file.relative_to(vault_root).with_suffix(".md")
    page_type = infer_type_for_import(rel_path, metadata, is_raw_import=True)
    metadata["type"] = page_type.value
    metadata["sources"] = [str(rel_path).replace("\\", "/")]
    metadata["provenance"] = "obsidian_canvas_import"
    final_content = serialize_frontmatter(metadata) + body.lstrip("\n")
    return ObsidianRawPrepared(
        relative_path=str(rel_path).replace("\\", "/"),
        content=final_content,
        metadata=metadata,
        images_copied=0,
    )
