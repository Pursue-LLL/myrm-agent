"""Typo Corrector

Fast dictionary-based spelling correction for common technical term typos.
Loads corrections from the ``typos`` section of ``config/synonyms.yaml``.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from .config_loader import ConfigLoader

logger = logging.getLogger(__name__)


class TypoCorrector:
    """Dictionary-based typo correction for technical terms"""

    def __init__(self, config_path: str | Path | None = None) -> None:
        """Initialize typo corrector

        [INPUT]

        [POS]
        The YAML file is the single source of truth for corrections; a missing or
        unreadable file leaves the corrector inert (ConfigLoader logs the reason).
        """
        self._corrections = {
            typo.lower(): fix for typo, fix in ConfigLoader.load_synonyms(config_path)["typos"].items()
        }
        logger.info(" Loaded %d typo corrections", len(self._corrections))

    def correct(self, query: str) -> str:
        """Correct common typos in query

        [INPUT]

        [OUTPUT]
        Corrected query

        [POS]
        Uses dictionary for fast, accurate correction; lookup ignores case.
        Returns original query if no typos found.
        """
        words = re.findall(r"\w+", query)
        corrected_words = [self._corrections.get(word.lower(), word) for word in words]

        if corrected_words != words:
            return " ".join(corrected_words)

        return query
