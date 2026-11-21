"""Meeting notes orchestration service.

[INPUT]
- app.services.wiki.source_sync.publish_helpers::publish_source_markdown, build_frontmatter, sanitize_path_segment (POS: wiki raw publish)

[OUTPUT]
- distill_meeting_notes(): LLM minutes distillation behind the live session's rolling and final notes
- publish_meeting_notes(): wiki raw publish of the final minutes

[POS]
Business orchestration facade for the meeting-notes pipeline. Delegates distillation to the
chat agent LLM and publication to the wiki raw pipeline. Contains zero LLM algorithm implementation.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import TYPE_CHECKING

from myrm_agent_harness.toolkits.wiki import WikiStructure

from app.services.meeting_notes.models import (
    MeetingActionItem,
    StructuredMeetingNotes,
)
from app.services.wiki.source_sync.publish_helpers import (
    build_frontmatter,
    publish_source_markdown,
    sanitize_path_segment,
)

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel

logger = logging.getLogger(__name__)

_WIKI_SOURCE_DIR = "meeting-notes"
# Upper bound for the title-collision suffix walk before falling back to a random one.
_MAX_MEETING_NOTE_COLLISIONS = 50

_SUMMARY_PROMPT_TEMPLATE = """You are a meeting-minutes extraction engine.
Given the full transcript of a meeting, produce:
1. A concise title (<=60 chars).
2. A 3-5 sentence summary.
3. Decisions made (bullets).
4. Key debate points (bullets).
5. Key risks or blockers (bullets).
6. Action items with optional owner and due hint.

Transcript:
{transcript}

Return strict JSON with keys: title, summary, decisions, debate_points, risks,
action_items (array of {{description, owner, due_hint}}). No markdown fences."""


async def distill_meeting_notes(transcript: str, llm: BaseChatModel | None) -> StructuredMeetingNotes:
    """LLM-distill decisions/debates/action items from transcript.

    Backs the rolling and final notes of the live pipeline (`live_notes.LiveNotesSession`).
    """
    if llm is None:
        return StructuredMeetingNotes(title="Meeting Notes", summary=transcript[:4000])
    prompt = _SUMMARY_PROMPT_TEMPLATE.format(transcript=transcript[:120000])
    response = await llm.ainvoke(prompt)
    content = getattr(response, "content", str(response))
    try:
        payload = json.loads(
            str(content).strip().removeprefix("```json").removesuffix("```").strip()
        )
    except (json.JSONDecodeError, ValueError):
        logger.warning(
            "Meeting notes LLM response was not valid JSON; falling back to raw summary"
        )
        return StructuredMeetingNotes(
            title="Meeting Notes", summary=str(content)[:4000]
        )
    if not isinstance(payload, dict):
        # Valid JSON that is not a minutes object (bare list/scalar): same degradation
        # path as unparsable output, so a chatty model never turns into a failed meeting.
        logger.warning("Meeting notes LLM response was not a JSON object; using raw summary")
        return StructuredMeetingNotes(title="Meeting Notes", summary=str(content)[:4000])
    return StructuredMeetingNotes(
        title=_as_title(payload.get("title")),
        summary=str(payload.get("summary") or ""),
        decisions=_as_text_tuple(payload.get("decisions")),
        debate_points=_as_text_tuple(payload.get("debate_points")),
        risks=_as_text_tuple(payload.get("risks")),
        action_items=_as_action_items(payload.get("action_items")),
    )


def _as_text_tuple(value: object) -> tuple[str, ...]:
    """Coerce one LLM list field into clean, non-empty strings.

    Real models return a bare string for a single-item list, ``null`` for "none", and
    occasionally nested structures. Without coercion a bare string would be iterated
    per character (one "risk" per letter) and ``null`` would raise, losing the meeting.
    """
    if value is None:
        return ()
    if isinstance(value, str):
        text = value.strip()
        return (text,) if text else ()
    if isinstance(value, (list, tuple)):
        return tuple(text for text in (str(item).strip() for item in value) if text)
    text = str(value).strip()
    return (text,) if text else ()


def _as_title(value: object) -> str:
    """Return a usable meeting title, never the literal ``"None"``."""
    text = str(value or "").strip()
    return text[:80] if text else "Meeting Notes"


def _as_action_items(value: object) -> tuple[MeetingActionItem, ...]:
    """Coerce the action-item field, accepting the shapes models actually emit."""
    if isinstance(value, (str, dict)):
        value = [value]
    if not isinstance(value, (list, tuple)):
        return ()
    items: list[MeetingActionItem] = []
    for raw in value:
        if isinstance(raw, dict):
            description = str(raw.get("description") or "").strip()
            owner = raw.get("owner") or None
            due_hint = raw.get("due_hint") or None
        elif isinstance(raw, str):
            description = raw.strip()
            owner, due_hint = None, None
        else:
            # Numbers/bools/nested lists are model noise, never an action item.
            continue
        if description:
            items.append(
                MeetingActionItem(description=description, owner=owner, due_hint=due_hint)
            )
    return tuple(items)


def _render_minutes_markdown(notes: StructuredMeetingNotes, transcript: str) -> str:
    """Render structured notes + transcript into wiki-ready Markdown body."""
    lines: list[str] = [f"# {notes.title}", "", "## Summary", notes.summary, ""]
    if notes.decisions:
        lines += ["## Decisions", *[f"- {d}" for d in notes.decisions], ""]
    if notes.debate_points:
        lines += ["## Key Debate Points", *[f"- {p}" for p in notes.debate_points], ""]
    if notes.risks:
        lines += ["## Risks", *[f"- {r}" for r in notes.risks], ""]
    if notes.action_items:
        lines += ["## Action Items"]
        lines += [
            f"- [ ] {item.description} (owner: {item.owner or 'TBD'}, due: {item.due_hint or 'TBD'})"
            for item in notes.action_items
        ]
        lines.append("")
    lines += ["## Transcript", transcript]
    return "\n".join(lines)


def _free_meeting_note_path(structure: WikiStructure, slug: str) -> str:
    """Return a free ``meeting-notes/<slug>.md`` path, suffixing on name collisions.

    The raw publish gate skips an existing path, so a recurring LLM-authored title
    would otherwise drop a whole meeting deliverable without any error. Suffixing keeps
    every meeting: the first note keeps the clean name, later ones get ``-2``, ``-3``…
    """
    candidate = f"{_WIKI_SOURCE_DIR}/{slug}.md"
    if not structure.get_raw_file_path(candidate).exists():
        return candidate
    for suffix in range(2, _MAX_MEETING_NOTE_COLLISIONS + 2):
        candidate = f"{_WIKI_SOURCE_DIR}/{slug}-{suffix}.md"
        if not structure.get_raw_file_path(candidate).exists():
            return candidate
    return f"{_WIKI_SOURCE_DIR}/{slug}-{uuid.uuid4().hex[:8]}.md"


async def publish_meeting_notes(
    structure: WikiStructure,
    notes: StructuredMeetingNotes,
    transcript: str,
    auto_compile: bool,
    compiler_enqueue: object | None,
) -> list[str]:
    """Publish minutes markdown into the wiki raw pipeline; returns published paths.

    Called when a live meeting session is finalized. The vault is chosen by the caller's
    ``structure``, so no agent id is needed here.
    """
    title = notes.title or "Meeting Notes"
    slug = sanitize_path_segment(f"meeting-{title}")
    relative_path = _free_meeting_note_path(structure, slug)
    content = (
        build_frontmatter(
            source="meeting_notes",
            title=title,
            external_id=f"meeting:{slug}",
            extra={"type": "meeting-notes"},
        )
        + "\n"
        + _render_minutes_markdown(notes, transcript)
    )
    published = await publish_source_markdown(
        structure,
        relative_path=relative_path,
        content=content,
        auto_compile=auto_compile,
        compiler_enqueue=compiler_enqueue,
    )
    # Report the vault-relative path only, and only for a real write: stringifying the
    # result object would leak the absolute local path and claim success for a skip.
    return [published.relative_path] if published.written else []
