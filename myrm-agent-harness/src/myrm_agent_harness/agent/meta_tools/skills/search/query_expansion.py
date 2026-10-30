"""Query Expansion Module

Orchestrates query enhancement through modular components:
- TypoCorrector: Spelling correction
- SynonymExpander: Synonym and multilingual expansion

[POS]
Adds recall for queries the caller wrote without the "concept/translation/synonym" format.
The caller's text is never rewritten: tokenization of camelCase, versions, URLs and
hyphenated names stays with ``preprocess_text``, which sees it as typed.
"""

from __future__ import annotations

import logging

from .synonym_expander import SynonymExpander
from .typo_corrector import TypoCorrector

logger = logging.getLogger(__name__)

MULTILINGUAL_FORMAT_DELIMITER = "/"
MAX_EXPANDED_QUERIES = 5


class QueryExpander:
    """Orchestrates query expansion pipeline

    Coordinates typo correction and synonym expansion.
    Adaptive strategy: skips synonym expansion for multilingual format queries.
    """

    def __init__(self) -> None:
        """Initialize query expansion pipeline"""
        self._typo_corrector = TypoCorrector()
        self._synonym_expander = SynonymExpander()

    def expand(self, query: str) -> list[str]:
        """Expand query through adaptive pipeline

        [INPUT]

        [OUTPUT]
        List of query variations; the first entry is the caller's query unchanged.

        [POS]
        Applies typo correction and conditional synonym expansion.
        Adaptive strategy: skips synonym expansion if query is multilingual format
        (e.g., "火车票/railway/train"), as LLM already provides rich semantic terms.
        Logs each transformation step for observability.
        """
        if not query.strip():
            return [query]

        expanded_queries = [query]

        corrected = self._typo_corrector.correct(query)
        if corrected != query:
            expanded_queries.append(corrected)
            logger.info(" [TypoCorrection] '%s' -> '%s'", query, corrected)

        if MULTILINGUAL_FORMAT_DELIMITER in query:
            logger.info(
                " [AdaptiveExpansion] Multilingual format detected in '%s' -> Skipping synonym expansion "
                "(LLM already provides rich semantic terms)",
                query,
            )
        else:
            before = len(expanded_queries)
            for variation in self._synonym_expander.expand(corrected):
                if variation not in expanded_queries:
                    expanded_queries.append(variation)
            if len(expanded_queries) > before:
                logger.info(
                    " [SynonymExpansion] '%s' -> +%d variations (total: %d)",
                    corrected,
                    len(expanded_queries) - before,
                    len(expanded_queries),
                )

        final_queries = expanded_queries[:MAX_EXPANDED_QUERIES]

        if len(final_queries) > 1:
            logger.info(
                " [QueryExpansion] '%s' -> %d variations: %s",
                query,
                len(final_queries),
                final_queries[:3],
            )

        return final_queries
