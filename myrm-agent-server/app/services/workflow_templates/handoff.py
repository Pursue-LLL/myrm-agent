"""TaskContextHandoff: thin material-passing spec between trunk flows.

[INPUT]
- Caller-built materials (title + excerpt) and intent strings

[OUTPUT]
- TaskContextHandoff: validated, immutable handoff record
- to_template_args: maps a handoff onto DW template `{placeholder}` args

[POS]
Handoff is a data schema only. Transport reuses the existing template_args /
chat-history / resume_value channels — no parallel state machine, no new I/O.
"""

from __future__ import annotations

from dataclasses import dataclass

_MAX_MATERIALS = 20
_MAX_EXCERPT_CHARS = 2000


@dataclass(frozen=True, slots=True)
class HandoffMaterial:
    """One piece of carried context: title plus verbatim excerpt."""

    title: str
    excerpt: str


@dataclass(frozen=True, slots=True)
class TaskContextHandoff:
    """Materials passed from a source flow into a target flow."""

    source_flow: str
    target_flow: str
    intent: str
    materials: tuple[HandoffMaterial, ...] = ()
    evidence_refs: tuple[str, ...] = ()


def build_handoff(
    *,
    source_flow: str,
    target_flow: str,
    intent: str,
    materials: list[tuple[str, str]] | None = None,
    evidence_refs: list[str] | None = None,
) -> TaskContextHandoff:
    """Normalize raw inputs into an immutable handoff (drops empties)."""
    kept_materials = tuple(
        HandoffMaterial(title=title.strip(), excerpt=excerpt.strip()[:_MAX_EXCERPT_CHARS])
        for title, excerpt in (materials or [])
        if title.strip() and excerpt.strip()
    )[:_MAX_MATERIALS]
    kept_refs = tuple(ref.strip() for ref in (evidence_refs or []) if ref.strip())
    return TaskContextHandoff(
        source_flow=source_flow.strip(),
        target_flow=target_flow.strip(),
        intent=intent.strip(),
        materials=kept_materials,
        evidence_refs=kept_refs,
    )


def validate_handoff(handoff: TaskContextHandoff) -> list[str]:
    """Return missing-field names; empty means the handoff is complete."""
    missing: list[str] = []
    if not handoff.source_flow:
        missing.append("source_flow")
    if not handoff.target_flow:
        missing.append("target")
    if not handoff.intent:
        missing.append("intent")
    if not handoff.materials:
        missing.append("materials")
    return missing


def to_template_args(
    handoff: TaskContextHandoff,
    extra: dict[str, str] | None = None,
) -> dict[str, str]:
    """Map a handoff onto DW template args (generic keys + caller extras)."""
    args: dict[str, str] = {
        "intent": handoff.intent,
        "context": "\n\n".join(f"[{m.title}]\n{m.excerpt}" for m in handoff.materials),
    }
    for key, value in (extra or {}).items():
        if value.strip():
            args[key.strip()] = value.strip()
    return {key: value for key, value in args.items() if value}
