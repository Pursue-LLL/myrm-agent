"""Knowledge pack and proactive injection data schemas.

[INPUT]
- None (pure domain dataclasses)

[OUTPUT]
- KnowledgePackConfig: Budget and dedup limits of one proactive injection.
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


@dataclass(frozen=True, slots=True)
class KnowledgePackConfig:
    """Budget and dedup limits of one proactive injection."""

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
