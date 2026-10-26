"""Markdown and privacy-safe rendering of exported memories.

[INPUT]
- None: pure functions over the serialized memory dicts that ``export_all`` yields

[OUTPUT]
- sanitize_paths_for_sharing: replaces home-directory paths with a ``<USER>/`` placeholder
- _memory_to_markdown: one memory dict as a Markdown file with type-specific YAML frontmatter
- _sanitize_filename: filesystem-safe file name derived from memory content
- _PERSONAL_FIELDS_TO_STRIP: personal counters and origins a shared rule must not carry

[POS]
Stateless rendering half of the import/export mixin: turns exported dicts into Markdown files and
privacy-safe rule text without touching any store.
"""

from __future__ import annotations

import re
from collections.abc import Callable

# ── Path sanitization for safe sharing ─────────────────────────────

_HOME_DIR_UNIX_RE = re.compile(r"(?:/Users/|/home/|/root/)[^\s/\"']+/")
_HOME_DIR_WIN_RE = re.compile(r"[A-Z]:\\Users\\[^\s\\\"']+\\")

_PERSONAL_FIELDS_TO_STRIP = frozenset(
    {
        "access_count",
        "user_rating",
        "source_chat_id",
    }
)


def sanitize_paths_for_sharing(text: str) -> str:
    """Replace home directory paths with generic <USER>/ placeholder.

    Only targets user home directories (/Users/xxx/, /home/xxx/, C:\\Users\\xxx\\).
    System paths (/usr/, /etc/, /opt/) are intentionally preserved.
    """
    if not text:
        return text
    text = _HOME_DIR_UNIX_RE.sub("<USER>/", text)
    text = _HOME_DIR_WIN_RE.sub("<USER>\\\\", text)
    return text


def _sanitize_filename(text: str, max_len: int = 60) -> str:
    """Create a safe filename from memory content."""
    clean = re.sub(r"[^\w\s\u4e00-\u9fff-]", "", text)
    clean = re.sub(r"\s+", "_", clean.strip())
    return clean[:max_len] if clean else "untitled"


def _extract_tags(metadata: object) -> list[str]:
    """Extract tags from memory metadata dict."""
    tags: list[str] = []
    if isinstance(metadata, dict):
        for k, v in metadata.items():
            if k == "tags" and isinstance(v, str):
                tags.extend(t.strip() for t in v.split(",") if t.strip())
            elif k == "category" and isinstance(v, str):
                tags.append(v)
    return tags


_RendererFn = Callable[
    [dict[str, object], str, str, str, str, str],
    str,
]


def _list_to_yaml_inline(items: list[object]) -> str:
    """Format a list as YAML inline sequence: [a, b, c]."""
    return f"[{', '.join(str(i) for i in items)}]"


def _yaml_safe_value(value: object) -> str:
    """Ensure a scalar value is safe for YAML frontmatter (no broken lines)."""
    s = str(value)
    if "\n" in s or "\r" in s:
        escaped = s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r")
        return f'"{escaped}"'
    return s


def _common_fields(memory_dict: dict[str, object]) -> tuple[str, str, str, str, str]:
    """Extract fields shared by all memory types."""
    mem_id = str(memory_dict.get("id", ""))
    content = str(memory_dict.get("content", ""))
    created_at = str(memory_dict.get("created_at", ""))
    updated_at = str(memory_dict.get("updated_at", ""))
    tags = _extract_tags(memory_dict.get("metadata", {}))
    tags_line = f"\ntags: [{', '.join(tags)}]" if tags else ""
    return mem_id, content, created_at, updated_at, tags_line


def _memory_to_markdown(memory_dict: dict[str, object], memory_type: str) -> str:
    """Convert a single memory dict to Markdown with YAML frontmatter.

    Each memory type has a dedicated renderer that includes its unique
    metadata fields in the frontmatter.  Unknown types fall back to a
    generic id/type/created_at/updated_at template.
    """
    mem_id, content, created_at, updated_at, tags_line = _common_fields(memory_dict)

    renderer = _TYPE_RENDERERS.get(memory_type)
    if renderer:
        return renderer(memory_dict, mem_id, content, created_at, updated_at, tags_line)

    frontmatter = (
        f"---\nid: {mem_id}\ntype: {memory_type}\ncreated_at: {created_at}\nupdated_at: {updated_at}{tags_line}\n---\n"
    )
    return f"{frontmatter}\n{content}\n"


def _procedural_to_markdown(
    d: dict[str, object],
    mem_id: str,
    content: str,
    created_at: str,
    updated_at: str,
    tags_line: str,
) -> str:
    """Render ProceduralMemory with full rule structure in frontmatter and body."""
    trigger = d.get("trigger", "")
    action = d.get("action", "")
    lines = [
        "---",
        f"id: {mem_id}",
        "type: procedural",
        f"trigger: {_yaml_safe_value(trigger)}",
        f"action: {_yaml_safe_value(action)}",
        f"priority: {d.get('priority', 0)}",
        f"source: {d.get('source', '')}",
        f"status: {d.get('status', '')}",
    ]
    language = d.get("language")
    if language:
        lines.append(f"language: {language}")
    tool_name = d.get("tool_name")
    if tool_name:
        lines.append(f"tool_name: {tool_name}")
        lines.append(f"tool_rule_priority: {d.get('tool_rule_priority', 'normal')}")
    if d.get("pinned"):
        lines.append("pinned: true")
    lines.append(f"access_count: {d.get('access_count', 0)}")
    lines.append(f"user_rating: {d.get('user_rating', 0.5)}")
    lines.append(f"created_at: {created_at}")
    lines.append(f"updated_at: {updated_at}{tags_line}")
    lines.append("---")

    body_parts: list[str] = []
    reasoning = d.get("reasoning")
    if reasoning:
        body_parts.append(f"## Reasoning\n\n{reasoning}")
    application = d.get("application")
    if application:
        body_parts.append(f"## Application\n\n{application}")
    body_parts.append(content)

    return "\n".join(lines) + "\n\n" + "\n\n".join(body_parts) + "\n"


def _semantic_to_markdown(
    d: dict[str, object],
    mem_id: str,
    content: str,
    created_at: str,
    updated_at: str,
    tags_line: str,
) -> str:
    """Render SemanticMemory with importance/confidence/preference metadata."""
    lines = [
        "---",
        f"id: {mem_id}",
        "type: semantic",
        f"importance: {d.get('importance', 0.5)}",
        f"confidence: {d.get('confidence', 1.0)}",
        f"language: {d.get('language', 'en')}",
    ]
    pref = d.get("preference_type")
    if pref:
        lines.append(f"preference_type: {pref}")
    src = d.get("source_chat_id")
    if src:
        lines.append(f"source_chat_id: {src}")
    sem_tags = d.get("tags")
    if isinstance(sem_tags, list) and sem_tags:
        lines.append(f"tags: {_list_to_yaml_inline(sem_tags)}")
    lines.append(f"created_at: {created_at}")
    lines.append(f"updated_at: {updated_at}{tags_line}")
    lines.append("---")
    return "\n".join(lines) + f"\n\n{content}\n"


def _episodic_to_markdown(
    d: dict[str, object],
    mem_id: str,
    content: str,
    created_at: str,
    updated_at: str,
    tags_line: str,
) -> str:
    """Render EpisodicMemory with event_type/importance/entities metadata."""
    lines = [
        "---",
        f"id: {mem_id}",
        "type: episodic",
        f"event_type: {d.get('event_type', 'conversation')}",
        f"importance: {d.get('importance', 0.5)}",
        f"language: {d.get('language', 'en')}",
    ]
    entities = d.get("related_entities")
    if isinstance(entities, list) and entities:
        lines.append(f"related_entities: {_list_to_yaml_inline(entities)}")
    lines.append(f"created_at: {created_at}")
    lines.append(f"updated_at: {updated_at}{tags_line}")
    lines.append("---")
    return "\n".join(lines) + f"\n\n{content}\n"


def _conversation_to_markdown(
    d: dict[str, object],
    mem_id: str,
    content: str,
    created_at: str,
    updated_at: str,
    tags_line: str,
) -> str:
    """Render ConversationMemory preserving raw_exchange in body."""
    lines = [
        "---",
        f"id: {mem_id}",
        "type: conversation",
        f"importance: {d.get('importance', 0.5)}",
        f"language: {d.get('language', 'en')}",
    ]
    for opt_key in ("project_id", "topic_id", "source_chat_id"):
        val = d.get(opt_key)
        if val:
            lines.append(f"{opt_key}: {val}")
    entities = d.get("related_entities")
    if isinstance(entities, list) and entities:
        lines.append(f"related_entities: {_list_to_yaml_inline(entities)}")
    lines.append(f"created_at: {created_at}")
    lines.append(f"updated_at: {updated_at}{tags_line}")
    lines.append("---")

    body_parts: list[str] = [f"## Summary\n\n{content}"]
    raw = d.get("raw_exchange")
    if raw:
        body_parts.append(f"## Original Exchange\n\n{raw}")
    return "\n".join(lines) + "\n\n" + "\n\n".join(body_parts) + "\n"


def _claim_to_markdown(
    d: dict[str, object],
    mem_id: str,
    content: str,
    created_at: str,
    updated_at: str,
    tags_line: str,
) -> str:
    """Render ClaimMemory with evidence/confidence metadata."""
    lines = [
        "---",
        f"id: {mem_id}",
        "type: claim",
        f"claim_key: {_yaml_safe_value(d.get('claim_key', ''))}",
        f"title: {_yaml_safe_value(d.get('title', ''))}",
        f"evidence_count: {d.get('evidence_count', 0)}",
        f"confidence: {d.get('confidence', 0.75)}",
        f"freshness: {d.get('freshness', 'stale')}",
        f"created_at: {created_at}",
        f"updated_at: {updated_at}{tags_line}",
        "---",
    ]
    body_parts: list[str] = []
    claim_text = d.get("claim_text")
    if claim_text:
        body_parts.append(f"## Claim\n\n{claim_text}")
    summary = d.get("model_summary")
    if summary:
        body_parts.append(f"## Summary\n\n{summary}")
    if content and content not in (claim_text, summary):
        body_parts.append(content)
    return "\n".join(lines) + "\n\n" + ("\n\n".join(body_parts) if body_parts else content) + "\n"


def _integration_to_markdown(
    d: dict[str, object],
    mem_id: str,
    content: str,
    created_at: str,
    updated_at: str,
    tags_line: str,
) -> str:
    """Render IntegrationMemory with provider/source metadata."""
    lines = [
        "---",
        f"id: {mem_id}",
        "type: integration",
        f"provider: {_yaml_safe_value(d.get('provider', ''))}",
        f"title: {_yaml_safe_value(d.get('title', ''))}",
        f"importance: {d.get('importance', 0.5)}",
    ]
    observed = d.get("observed_at")
    if observed:
        lines.append(f"observed_at: {observed}")
    int_tags = d.get("tags")
    if isinstance(int_tags, list) and int_tags:
        lines.append(f"tags: {_list_to_yaml_inline(int_tags)}")
    lines.append(f"created_at: {created_at}")
    lines.append(f"updated_at: {updated_at}{tags_line}")
    lines.append("---")

    body_parts: list[str] = []
    summary = d.get("summary")
    if summary:
        body_parts.append(f"## Summary\n\n{summary}")
    if content and content != summary:
        body_parts.append(content)
    return "\n".join(lines) + "\n\n" + ("\n\n".join(body_parts) if body_parts else content) + "\n"


_TYPE_RENDERERS: dict[str, _RendererFn] = {
    "procedural": _procedural_to_markdown,
    "semantic": _semantic_to_markdown,
    "episodic": _episodic_to_markdown,
    "conversation": _conversation_to_markdown,
    "claim": _claim_to_markdown,
    "integration": _integration_to_markdown,
}
