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

# Markdown section headings (bold ``**Title**`` or ATX ``# Title``), optionally
# followed by inline text on the same line (``**Goal** — one sentence``).
_HEADING_RE = re.compile(r"^\s*(?:\*{1,3}\s*[^*]+\*{1,3}|#{1,6}\s+.+)\s*(?:[—-]?\s*.*)?$")

# Acceptance-criteria heading, EN/ZH. Anchored case-insensitively so LLMs
# writing ``**acceptance criteria**`` / ``**验收条件**`` / ``**验收标准**``
# all match.
_ACCEPTANCE_RE = re.compile(
    r"^\s*(?:\*{1,3}\s*)?(?:acceptance\s*criteria|验收条件|验收标准)\s*(?:\*{1,3})?\s*(?:[—-]?\s*.*)?$",
    re.IGNORECASE,
)

_MAX_CRITERIA = 6


def parse_markdown_criteria(body: str | None) -> list[dict[str, str]]:
    """Extract ``- [ ]``/``- [x]`` checklist lines from markdown *body*.

    When the body has an explicit ``**Acceptance criteria**`` (or ``验收条件`` /
    ``验收标准``) heading, only checklist lines *inside that section* are taken —
    process-style checklists the LLM may write under ``**Approach**`` are
    excluded so they cannot become bogus acceptance gates. If no acceptance
    heading is found, every checklist line is returned (backward-compatible
    fallback).

    Returns a list of ``{"type": "semantic", "criteria": "<line>"}`` dicts.
    Blank or whitespace-only lines are skipped. Lines are capped at
    ``_MAX_CRITERIA`` so a noisy spec cannot blow the verifier prompt. Empty
    results (no checklist present) mean the caller should leave
    ``completion_criteria`` untouched.
    """
    if not body:
        return []

    lines = body.splitlines()
    acceptance_idx = _find_acceptance_section(lines)

    if acceptance_idx is None:
        # No acceptance heading: backward-compatible global scan.
        return _collect_criteria(lines, 0, len(lines))

    # Section mode: only the checklist between the acceptance heading and the
    # next markdown heading (or end of body).
    end = len(lines)
    for i in range(acceptance_idx + 1, len(lines)):
        if _HEADING_RE.match(lines[i]):
            end = i
            break
    return _collect_criteria(lines, acceptance_idx + 1, end)


def _find_acceptance_section(lines: list[str]) -> int | None:
    """Return the index of the acceptance-criteria heading, or None."""
    for i, line in enumerate(lines):
        if _HEADING_RE.match(line) and _ACCEPTANCE_RE.match(line):
            return i
    return None


def _collect_criteria(
    lines: list[str],
    start: int,
    end: int,
) -> list[dict[str, str]]:
    """Collect checklist lines in ``lines[start:end]`` into semantic criteria."""
    criteria: list[dict[str, str]] = []
    for i in range(start, end):
        match = _CHECKLIST_RE.match(lines[i])
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
