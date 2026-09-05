"""Helper utilities for probing and dry-run previewing local skill paths."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from myrm_agent_harness.api.skills import parse_skill_frontmatter

from ..models import Skill

logger = logging.getLogger(__name__)

SKILL_MD_FILE = "SKILL.md"
_MAX_SKILL_FILE_SIZE = 1 * 1024 * 1024  # 1 MB


def _extract_skill_preview(
    skill_dir: Path,
    rel_path: str,
    existing_names: dict[str, Skill],
    compute_id_fn: callable,
) -> dict[str, object] | None:
    skill_md = skill_dir / SKILL_MD_FILE
    if not skill_md.is_file():
        return None
    try:
        content = skill_md.read_text(encoding="utf-8")
        if len(content.encode("utf-8")) > _MAX_SKILL_FILE_SIZE:
            return None
        frontmatter = parse_skill_frontmatter(content, skill_dir.name)
    except Exception as e:
        logger.debug("Failed to parse SKILL.md in %s: %s", skill_dir, e)
        return None

    skill_name = str(frontmatter.name or skill_dir.name)
    description = str(frontmatter.description or "")
    version = str(frontmatter.version or "1.0.0")
    category = str(frontmatter.category) if frontmatter.category else None

    tags: list[str] = []
    if hasattr(frontmatter, "tags") and isinstance(getattr(frontmatter, "tags"), list):
        tags = [str(t) for t in getattr(frontmatter, "tags")]
    elif isinstance(frontmatter.metadata, dict) and "tags" in frontmatter.metadata:
        raw_tags = frontmatter.metadata["tags"]
        if isinstance(raw_tags, list):
            tags = [str(t) for t in raw_tags]
        elif isinstance(raw_tags, str):
            tags = [t.strip() for t in raw_tags.split(",") if t.strip()]

    author: str | None = None
    if isinstance(frontmatter.metadata, dict) and "author" in frontmatter.metadata:
        author = str(frontmatter.metadata["author"])

    required_tools: list[str] = []
    if frontmatter.requires and hasattr(frontmatter.requires, "bins") and isinstance(frontmatter.requires.bins, list):
        required_tools = [str(b) for b in frontmatter.requires.bins]

    skill_id = compute_id_fn(skill_dir)

    norm_name = skill_name.strip().lower()
    is_conflicted = False
    conflict_reason: str | None = None
    if norm_name in existing_names:
        is_conflicted = True
        conflicted_skill = existing_names[norm_name]
        conflict_reason = f"Conflicts with existing {conflicted_skill.type.value} skill '{conflicted_skill.name}'"

    is_safe = True
    threat_summary: str | None = None
    try:
        from myrm_agent_harness.backends.skills.scanning import scan_skill_content

        scan_res = scan_skill_content(skill_name, content)
        if not scan_res.is_clean:
            is_safe = False
            threat_summary = f"{len(scan_res.findings)} potential security findings detected"
    except Exception as scan_err:
        logger.debug("Security scan skipped for %s: %s", skill_name, scan_err)

    return {
        "name": skill_name,
        "description": description,
        "version": version,
        "author": author,
        "category": category,
        "tags": tags,
        "required_tools": required_tools,
        "relative_path": rel_path,
        "skill_id": skill_id,
        "is_conflicted": is_conflicted,
        "conflict_reason": conflict_reason,
        "is_safe": is_safe,
        "threat_summary": threat_summary,
    }


def preview_skill_path(
    raw_path: str,
    existing_skills: list[Skill] | None = None,
    max_scan_entries: int = 100,
    compute_id_fn: callable = None,
) -> tuple[Path, bool, bool, list[dict[str, object]], str | None]:
    """Dry-run probe a path for local skills without modifying provider state."""
    expanded_path = Path(os.path.expanduser(raw_path)).resolve()
    if not expanded_path.exists():
        return expanded_path, False, False, [], "Path does not exist"
    if not expanded_path.is_dir():
        return expanded_path, True, False, [], "Path is not a directory"

    items: list[dict[str, object]] = []
    warning_msg: str | None = None

    existing_names: dict[str, Skill] = {}
    if existing_skills:
        for s in existing_skills:
            existing_names[s.name.strip().lower()] = s

    # Case 1: The path itself is directly a skill directory
    if (expanded_path / SKILL_MD_FILE).is_file():
        single_preview = _extract_skill_preview(expanded_path, ".", existing_names, compute_id_fn)
        if single_preview:
            items.append(single_preview)
        return expanded_path, True, True, items, warning_msg

    # Case 2: Parent directory containing skill subdirectories
    count = 0
    try:
        for item in sorted(expanded_path.iterdir()):
            count += 1
            if count > max_scan_entries:
                warning_msg = f"Directory exceeds maximum preview limit of {max_scan_entries} entries; partial results shown."
                break

            if not item.is_dir():
                continue

            sub_preview = _extract_skill_preview(item, item.name, existing_names, compute_id_fn)
            if sub_preview:
                items.append(sub_preview)
    except PermissionError:
        return expanded_path, True, True, [], "Permission denied accessing directory"
    except Exception as e:
        logger.warning("Failed to scan directory %s during preview: %s", expanded_path, e)
        return expanded_path, True, True, [], f"Scan error: {e}"

    return expanded_path, True, True, items, warning_msg
