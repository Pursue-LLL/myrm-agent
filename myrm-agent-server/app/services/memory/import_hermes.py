"""Hermes memory import adapter.

[INPUT]
Hermes data payload with Markdown-based memory/soul/user files and optional skill data.

Expected payload keys (memory lane only; instruction keys are stripped before this adapter runs):
  - ``memory_md``: str — MEMORY.md factual memories
  - ``user_md``: str — USER.md user profile/preferences
  - ``skills``: list[dict] — skill definitions from skills/ directory
  - ``env_keys``: list[dict] — detected API key env var names (info only)
  - ``_source``: "hermes" — source identifier

[OUTPUT]
MemoryImportDryRunResult mapping Hermes data to native semantic/profile/persona/procedural buckets.

[POS]
Hermes competitor import adapter. Maps MEMORY.md and USER.md into semantic/profile
memory buckets for the dry-run → confirm → rollback pipeline.
"""

from __future__ import annotations

import re

from myrm_agent_harness.toolkits.memory import (
    MemoryImportDryRunResult,
    MemoryImportMappingItem,
)

from app.services.memory.import_adapter_utils import (
    build_metadata,
    build_result,
    iso_or_now,
)

_MEMORY_LINE_PATTERN = re.compile(r"^[-*]\s+(.+)$", re.MULTILINE)
_SECTION_HEADER_PATTERN = re.compile(r"^#{1,3}\s+(.+)$", re.MULTILINE)


def dry_run_hermes(payload: dict[str, object]) -> MemoryImportDryRunResult:
    """Map a Hermes data payload into native memory buckets without persisting."""

    normalized: dict[str, list[dict[str, object]]] = {}
    mappings: list[MemoryImportMappingItem] = []
    warnings: list[str] = []
    mapped_items = 0
    unmapped_items = 0

    soul_md = _get_str(payload, "soul_md")
    if soul_md:
        persona_items = _parse_soul_md(soul_md)
        if persona_items:
            normalized.setdefault("profile", []).extend(persona_items)
            mapped_items += len(persona_items)
        mappings.append(
            MemoryImportMappingItem(
                source_bucket="SOUL.md",
                target_bucket="profile",
                status="mapped" if persona_items else "unsupported",
                item_count=1,
                imported_count=len(persona_items),
                reason="" if persona_items else "SOUL.md was empty or unparseable.",
            )
        )

    memory_md = _get_str(payload, "memory_md")
    if memory_md:
        semantic_items = _parse_memory_md(memory_md)
        if semantic_items:
            normalized.setdefault("semantic", []).extend(semantic_items)
            mapped_items += len(semantic_items)
        mappings.append(
            MemoryImportMappingItem(
                source_bucket="MEMORY.md",
                target_bucket="semantic",
                status="mapped" if semantic_items else "unsupported",
                item_count=max(len(semantic_items), 1),
                imported_count=len(semantic_items),
                reason="" if semantic_items else "MEMORY.md was empty or unparseable.",
            )
        )

    user_md = _get_str(payload, "user_md")
    if user_md:
        profile_items = _parse_user_md(user_md)
        if profile_items:
            normalized.setdefault("profile", []).extend(profile_items)
            mapped_items += len(profile_items)
        mappings.append(
            MemoryImportMappingItem(
                source_bucket="USER.md",
                target_bucket="profile",
                status="mapped" if profile_items else "unsupported",
                item_count=max(len(profile_items), 1),
                imported_count=len(profile_items),
                reason="" if profile_items else "USER.md was empty or unparseable.",
            )
        )

    agents_md = _get_str(payload, "agents_md")
    if agents_md:
        unmapped_items += 1
        mappings.append(
            MemoryImportMappingItem(
                source_bucket="AGENTS.md",
                status="unsupported",
                item_count=1,
                unmapped_count=1,
                reason="AGENTS.md is agent configuration; archived for manual review only.",
            )
        )

    skills = payload.get("skills")
    if isinstance(skills, list) and skills:
        skill_items = _parse_skills(skills)
        unmapped_items += len(skill_items)
        mappings.append(
            MemoryImportMappingItem(
                source_bucket="skills",
                status="unsupported",
                item_count=len(skill_items),
                unmapped_count=len(skill_items),
                reason="Skills are migrated through the skill migration review pipeline, not the memory import path.",
            )
        )
        warnings.append("hermes_skills_detected")

    env_keys = payload.get("env_keys")
    if isinstance(env_keys, list) and env_keys:
        warnings.append("hermes_api_keys_detected")

    return build_result(
        source="hermes",
        version="1",
        normalized=normalized,
        mappings=mappings,
        mapped_items=mapped_items,
        unmapped_items=unmapped_items,
        warnings=warnings,
    )


def _get_str(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    return value.strip() if isinstance(value, str) else ""


def _parse_soul_md(content: str) -> list[dict[str, object]]:
    """Parse SOUL.md into a single profile-type persona memory."""

    content = content.strip()
    if not content:
        return []
    return [
        {
            "content": content,
            "memory_type": "profile",
            "importance": 0.9,
            "confidence": 0.8,
            "tags": ["persona", "hermes_soul"],
            "created_at": iso_or_now(None),
            "metadata": build_metadata("hermes", {"file": "SOUL.md"}, ("file",)),
        }
    ]


def _parse_memory_md(content: str) -> list[dict[str, object]]:
    """Parse MEMORY.md into individual semantic memory items (one per bullet)."""

    items: list[dict[str, object]] = []
    current_section = ""

    for line in content.split("\n"):
        line = line.strip()
        section_match = _SECTION_HEADER_PATTERN.match(line)
        if section_match:
            current_section = section_match.group(1).strip()
            continue

        item_match = _MEMORY_LINE_PATTERN.match(line)
        if item_match:
            text = item_match.group(1).strip()
            if text:
                tags = ["hermes_memory"]
                if current_section:
                    tags.append(current_section.lower().replace(" ", "_"))
                items.append(
                    {
                        "content": text,
                        "importance": 0.7,
                        "confidence": 0.75,
                        "tags": tags,
                        "created_at": iso_or_now(None),
                        "metadata": build_metadata(
                            "hermes", {"file": "MEMORY.md", "section": current_section}, ("file", "section")
                        ),
                    }
                )

    if not items and content.strip():
        items.append(
            {
                "content": content.strip(),
                "importance": 0.7,
                "confidence": 0.7,
                "tags": ["hermes_memory"],
                "created_at": iso_or_now(None),
                "metadata": build_metadata("hermes", {"file": "MEMORY.md"}, ("file",)),
            }
        )

    return items


def _parse_user_md(content: str) -> list[dict[str, object]]:
    """Parse USER.md into profile memory items."""

    items: list[dict[str, object]] = []

    for line in content.split("\n"):
        line = line.strip()
        item_match = _MEMORY_LINE_PATTERN.match(line)
        if item_match:
            text = item_match.group(1).strip()
            if text:
                items.append(
                    {
                        "content": text,
                        "memory_type": "profile",
                        "importance": 0.8,
                        "confidence": 0.8,
                        "tags": ["hermes_user", "preference"],
                        "created_at": iso_or_now(None),
                        "metadata": build_metadata("hermes", {"file": "USER.md"}, ("file",)),
                    }
                )

    if not items and content.strip():
        items.append(
            {
                "content": content.strip(),
                "memory_type": "profile",
                "importance": 0.8,
                "confidence": 0.75,
                "tags": ["hermes_user"],
                "created_at": iso_or_now(None),
                "metadata": build_metadata("hermes", {"file": "USER.md"}, ("file",)),
            }
        )

    return items


def _parse_skills(skills: list[object]) -> list[dict[str, object]]:
    """Extract skill metadata for mapping info (not imported via memory path)."""

    return [{"name": skill.get("name", "unknown"), "source": "hermes"} for skill in skills if isinstance(skill, dict)]
