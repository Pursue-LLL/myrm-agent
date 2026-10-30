"""Synonym Expander

Expands queries with synonyms and related terms for improved recall.
Supports both English technical terms and Chinese semantic mappings.
Loads mappings from ``config/synonyms.yaml``.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from .config_loader import ConfigLoader

logger = logging.getLogger(__name__)

_CJK_CHAR = re.compile(r"[\u4e00-\u9fff]")


def _term_in_query(term: str, query: str) -> bool:
    """Match whole terms only — avoid substring hits like auth inside authenticate."""
    if _CJK_CHAR.search(term):
        return term in query
    pattern = rf"(?<!\w){re.escape(term)}(?!\w)"
    return re.search(pattern, query, flags=re.IGNORECASE) is not None


def _replace_term(query: str, term: str, synonym: str) -> str:
    """Replace one whole-term occurrence; CJK uses literal substring replacement."""
    if _CJK_CHAR.search(term):
        return re.sub(re.escape(term), synonym, query, count=1, flags=re.IGNORECASE)
    pattern = rf"(?<!\w){re.escape(term)}(?!\w)"
    return re.sub(pattern, synonym, query, count=1, flags=re.IGNORECASE)


class SynonymExpander:
    """Synonym expansion for technical terms and concepts"""

    def __init__(self, config_path: str | Path | None = None) -> None:
        """Initialize synonym expander

        [INPUT]

        [POS]
        ``config/synonyms.yaml`` is the single source of truth for synonym mappings; a
        missing or unreadable file leaves the expander inert (ConfigLoader logs the reason).
        """
        config = ConfigLoader.load_synonyms(config_path)
        self._all_synonyms = {**config["english"], **config["chinese"]}
        logger.info(
            " Loaded %d synonym mappings (%d EN + %d ZH)",
            len(self._all_synonyms),
            len(config["english"]),
            len(config["chinese"]),
        )

    def expand(self, query: str) -> list[str]:
        """Expand query with synonyms

        [INPUT]

        [OUTPUT]
        List of query variations including synonyms

        [POS]
        Generates multiple query variations by substituting synonyms.
        Limits to top 5 variations to avoid explosion.
        """
        if not query.strip():
            return [query]

        expanded_queries = [query]

        # Expand with synonyms
        for term, synonyms in self._all_synonyms.items():
            if not _term_in_query(term, query):
                continue
            for synonym in synonyms:
                if synonym == term:
                    continue
                expanded_query = _replace_term(query, term, synonym)
                if expanded_query not in expanded_queries:
                    expanded_queries.append(expanded_query)

        # Limit to top 5 variations to avoid explosion
        return expanded_queries[:5]
