"""Knowledge Pack domain module facade.

[INPUT]
- app.services.wiki.knowledge_pack.schemas::KnowledgePackConfig, RelevantSnippet, ProactiveKnowledgeResult
- app.services.wiki.knowledge_pack.selector::KnowledgePackSelector, calculate_jaccard_similarity, resolve_proactive_snippets_from_vaults

[OUTPUT]
- Facade exports for Knowledge Pack schemas and selector.

[POS]
Clean facade export for Knowledge Pack proactive turn injection.
"""

from __future__ import annotations

from app.services.wiki.knowledge_pack.schemas import (
    KnowledgePackConfig,
    ProactiveKnowledgeResult,
    RelevantSnippet,
)
from app.services.wiki.knowledge_pack.selector import (
    KnowledgePackSelector,
    calculate_jaccard_similarity,
    resolve_proactive_snippets_from_vaults,
    truncate_snippet_text,
)

__all__ = [
    "KnowledgePackConfig",
    "KnowledgePackSelector",
    "ProactiveKnowledgeResult",
    "RelevantSnippet",
    "calculate_jaccard_similarity",
    "resolve_proactive_snippets_from_vaults",
    "truncate_snippet_text",
]
