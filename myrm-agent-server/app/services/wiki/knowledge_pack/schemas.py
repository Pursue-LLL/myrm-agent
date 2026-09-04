"""Knowledge pack and proactive injection data schemas.

[INPUT]
- None (pure domain dataclasses)

[OUTPUT]
- KnowledgePackConfig: Lightweight composite container for agent/session knowledge binding.
- RelevantSnippet: High-confidence paragraph-level citation extracted from knowledge bases.
- ProactiveKnowledgeResult: Container for turn-level proactive injection payload.

[POS]
Domain contract for Proactive Knowledge Pack turn injection.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class RelevantSnippet:
    """Paragraph-level snippet extracted from a mounted knowledge base."""

    kb_name: str
    article_title: str
    snippet: str
    confidence: float
    source_path: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "kb_name": self.kb_name,
            "article_title": self.article_title,
            "snippet": self.snippet,
            "confidence": self.confidence,
            "source_path": self.source_path,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> RelevantSnippet:
        return cls(
            kb_name=str(data.get("kb_name", "Wiki")),
            article_title=str(data.get("article_title", "")),
            snippet=str(data.get("snippet", "")),
            confidence=float(data.get("confidence", 1.0)),  # type: ignore[arg-type]
            source_path=str(data.get("source_path", "")),
        )


@dataclass(frozen=True, slots=True)
class KnowledgePackConfig:
    """Lightweight composite container configuring proactive knowledge injection."""

    pack_id: str
    name: str
    shared_context_ids: list[str] = field(default_factory=list)
    procedural_rules: list[str] = field(default_factory=list)
    max_snippets: int = 3
    max_chars_per_snippet: int = 200
    max_total_chars: int = 600
    dedup_threshold: float = 0.70


@dataclass(frozen=True, slots=True)
class ProactiveKnowledgeResult:
    """Execution result of proactive knowledge retrieval for a turn."""

    snippets: list[RelevantSnippet] = field(default_factory=list)
    total_chars: int = 0
    latency_ms: float = 0.0
    is_truncated: bool = False
    source_count: int = 0

    def to_dict(self) -> dict[str, object]:
        return {
            "snippets": [s.to_dict() for s in self.snippets],
            "total_chars": self.total_chars,
            "latency_ms": self.latency_ms,
            "is_truncated": self.is_truncated,
            "source_count": self.source_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> ProactiveKnowledgeResult:
        raw_snippets = data.get("snippets")
        snippets = (
            [RelevantSnippet.from_dict(item) for item in raw_snippets if isinstance(item, dict)]
            if isinstance(raw_snippets, list)
            else []
        )
        return cls(
            snippets=snippets,
            total_chars=int(data.get("total_chars", 0)),  # type: ignore[arg-type]
            latency_ms=float(data.get("latency_ms", 0.0)),  # type: ignore[arg-type]
            is_truncated=bool(data.get("is_truncated", False)),
            source_count=int(data.get("source_count", 0)),  # type: ignore[arg-type]
        )
