"""Obsidian Vault adapter for Wiki import.

[INPUT]
myrm_agent_harness.toolkits.wiki.core.structure::WikiFileStructure (POS: Wiki file layout and scanning)

[OUTPUT]
adapt_obsidian_file: Transforms Obsidian-specific syntax before Wiki ingestion.

[POS]
Business-layer adapter that pre-processes Obsidian Vault files for compatibility with the
harness Wiki pipeline. Handles YAML frontmatter extraction, embedded image references
(![[img]]), and content normalization. Delegates actual import to the existing scan_folder
+ WikiCompiler flow.
"""

from __future__ import annotations

import logging
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
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


def parse_frontmatter(content: str) -> tuple[dict[str, object], str]:
    """Extract YAML frontmatter from Markdown content.

    Returns (metadata_dict, body_without_frontmatter).
    Supports both inline arrays (`tags: [a, b]`) and YAML indented lists
    (`tags:\\n  - a\\n  - b`), which is the most common format in Obsidian.
    """
    match = _FRONTMATTER_RE.match(content)
    if not match:
        return {}, content

    raw_fm = match.group(1)
    body = content[match.end() :]
    metadata: dict[str, object] = {}
    current_list_key: str | None = None
    current_list: list[str] = []

    def _flush_list() -> None:
        nonlocal current_list_key, current_list
        if current_list_key and current_list:
            metadata[current_list_key] = current_list
        current_list_key = None
        current_list = []

    for raw_line in raw_fm.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        if stripped.startswith("- ") and current_list_key is not None:
            current_list.append(stripped[2:].strip().strip("'\""))
            continue

        _flush_list()

        if ":" not in stripped:
            continue

        key, _, value = stripped.partition(":")
        key = key.strip().lower()
        value = value.strip()

        if not value:
            current_list_key = key
            current_list = []
        elif value.startswith("[") and value.endswith("]"):
            items = [v.strip().strip("'\"") for v in value[1:-1].split(",") if v.strip()]
            metadata[key] = items
        elif value.startswith("'") or value.startswith('"'):
            metadata[key] = value.strip("'\"")
        else:
            metadata[key] = value

    _flush_list()
    return metadata, body


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
        return None, {}, 0

    try:
        content = source_file.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            content = source_file.read_text(encoding="latin-1")
        except Exception:
            return None, {}, 0

    metadata, body = parse_frontmatter(content)
    body, images_copied = rewrite_image_embeds(body, source_file, vault_root, assets_dest)

    if metadata.get("tags"):
        tags = metadata["tags"]
        if isinstance(tags, list):
            tag_line = "Tags: " + ", ".join(str(t) for t in tags)
        else:
            tag_line = f"Tags: {tags}"
        body = f"{tag_line}\n\n{body}"

    if metadata.get("aliases"):
        aliases = metadata["aliases"]
        if isinstance(aliases, list):
            alias_line = "Aliases: " + ", ".join(str(a) for a in aliases)
        else:
            alias_line = f"Aliases: {aliases}"
        body = f"{alias_line}\n\n{body}"

    rel_path = source_file.relative_to(vault_root)
    dest_path = raw_dest_dir / rel_path
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    dest_path.write_text(body, encoding="utf-8")

    return dest_path, metadata, images_copied
