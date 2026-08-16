"""Markdown acceptance-criteria parser for Kanban specify/decompose.

Extracts ``- [ ]`` / ``- [x]`` checklist lines from LLM-generated task specs
(``**Acceptance criteria**`` section) and maps them to the structured
``completion_criteria`` metadata shape consumed by ``KanbanCompletionVerifier``
and goal-mode ``_setup_goal_provider``.

The output schema mirrors the established text→criteria pattern in
``app/core/channel_bridge/goal_handler._parse_im_goal_text`` (:56), keeping
Kanban on the same ``{"type": "semantic", "criteria": ...}`` shape.

[INPUT]
- raw markdown body from ``SpecifyOutcome.new_body`` / ``DecomposeChildSpec.body``

[OUTPUT]
- parse_markdown_criteria: ``list[dict[str, str]]`` of semantic criteria.
- attach_completion_criteria: attach parsed criteria to task metadata dict.

Note: the checklist is the natural-language acceptance contract written by the
LLM. We intentionally emit ``semantic`` (never ``shell``) — converting free-text
lines into shell commands would be an unreliable guess; the semantic judge
covers machine-checkable items too.
"""

from __future__ import annotations

import re

_CHECKLIST_RE = re.compile(r"^\s*(?:[-*]|\.{0,3}\d+[.)])\s*\[([ xX])\]\s*(.+)$")

_MAX_CRITERIA = 6


def parse_markdown_criteria(body: str | None) -> list[dict[str, str]]:
    """Extract ``- [ ]``/``- [x]`` checklist lines from markdown *body*.

    Returns a list of ``{"type": "semantic", "criteria": "<line>"}`` dicts.
    Blank or whitespace-only lines are skipped. Lines are capped at
    ``_MAX_CRITERIA`` so a noisy spec cannot blow the verifier prompt. Empty
    results (no checklist present) mean the caller should leave
    ``completion_criteria`` untouched.
    """
    if not body:
        return []

    criteria: list[dict[str, str]] = []
    for line in body.splitlines():
        match = _CHECKLIST_RE.match(line)
        if match is None:
            continue
        text = match.group(2).strip()
        if not text:
            continue
        criteria.append({"type": "semantic", "criteria": text})
        if len(criteria) >= _MAX_CRITERIA:
            break
    return criteria


def attach_completion_criteria(
    metadata: dict[str, object],
    body: str | None,
) -> dict[str, object]:
    """Return *metadata* with parsed ``completion_criteria`` attached.

    Pure function — never mutates the input dict. A user-provided
    ``completion_criteria`` already present in *metadata* always wins over the
    LLM-derived checklist, and an empty parse result leaves metadata untouched.
    """
    if "completion_criteria" in metadata:
        return metadata
    criteria = parse_markdown_criteria(body)
    if not criteria:
        return metadata
    merged = dict(metadata)
    merged["completion_criteria"] = criteria
    return merged
