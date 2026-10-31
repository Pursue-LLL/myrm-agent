"""The terms a question searches the knowledge pack by, and whether a page paragraph answers it.

[INPUT]
- myrm_agent_harness.api::STOP_WORDS (POS: the English and Chinese words every wiki query drops)

[OUTPUT]
- MAX_QUERY_CHARS: Length of the question prefix the pack reads.
- ordered_terms: Alphanumeric words plus CJK unigrams and bigrams, each once, in the order they appear.
- tokenize_text: The same terms as a set.
- search_terms: The terms a question searches by: stop words dropped, capped, in question order.
- carried_terms: How many search terms a text carries: CJK terms as substrings, words as whole words or word starts.
- paragraph_relevance: Share of the search terms a page title and paragraph carry; 0.0 when too few.

[POS]
One definition of the question's terms for both retrieval tiers: the index query, the paragraph pick and the
relevance floor all read the same list, so a question gives the same terms in every process and a paragraph is
scored the same whichever tier found it.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from functools import lru_cache

from myrm_agent_harness.api import STOP_WORDS

MAX_QUERY_CHARS = 1000
_MAX_SEARCH_TERMS = 16
_EN_NUM_PATTERN = re.compile(r"[a-z0-9]+", re.ASCII)


def ordered_terms(text: str) -> list[str]:
    """Alphanumeric words plus CJK unigrams and bigrams, each once, in the order they appear in ``text``."""
    cleaned = text.lower()
    found: list[tuple[int, int, str]] = [(m.start(), 0, m.group(0)) for m in _EN_NUM_PATTERN.finditer(cleaned)]
    cjk_chars = [(i, c) for i, c in enumerate(cleaned) if "\u4e00" <= c <= "\u9fa5"]
    found.extend((i, 1, c) for i, c in cjk_chars)
    found.extend((i, 2, a + b) for (i, a), (_, b) in zip(cjk_chars, cjk_chars[1:], strict=False))
    return list(dict.fromkeys(term for _, _, term in sorted(found)))


def tokenize_text(text: str) -> set[str]:
    """Tokenize text into alphanumeric words and CJK unigrams + bigrams."""
    return set(ordered_terms(text))


def search_terms(query: str) -> list[str]:
    """The first sixteen terms of ``query`` that are not stop words, in the order they appear.

    Terms are words of two or more characters and CJK bigrams; single characters are used only when nothing longer
    is left. Stop words are dropped before the cap, so the filler of a polite question ("could you please tell me
    about ...", or its Chinese equivalents) never uses up the slots that carry its subject.
    """
    terms = [t for t in ordered_terms(query) if t not in STOP_WORDS]
    longer = [t for t in terms if len(t) >= 2]
    return (longer or terms)[:_MAX_SEARCH_TERMS]


@lru_cache(maxsize=1024)
def _word_pattern(term: str) -> re.Pattern[str]:
    """A word as the index sees it: a run of letters and digits. From four characters on it may be the start of a
    longer word, so ``agent`` is carried by ``agents``; a shorter word is carried only as a whole word."""
    end = "" if len(term) >= 4 else "(?![a-z0-9])"
    return re.compile(f"(?<![a-z0-9]){re.escape(term)}{end}")


def carried_terms(terms: Sequence[str], text: str) -> int:
    """How many of ``terms`` the lowercased ``text`` carries.

    A short word inside a longer one does not count (``me`` is not in ``memory``, ``my`` is not in a product name),
    which is how the index matches it too; counting substrings lets two such words make any paragraph look relevant.
    """
    return sum(1 for t in terms if (_word_pattern(t).search(text) if t.isascii() else t in text))


def paragraph_relevance(terms: Sequence[str], title: str, paragraph: str) -> float:
    """The share of ``terms`` found in the page title and the paragraph, or 0.0 when the page does not answer them.

    Two terms must be found (all of them when the question has fewer), and either three or one of them in the title:
    common words co-occur in unrelated paragraphs, while a title names what a page is about. An index returns its
    best pages for any question, answered or not; this is the floor under it.
    """
    if not terms:
        return 0.0
    title_text = title.lower()
    haystack = f"{title_text} {paragraph.lower()}"
    found = carried_terms(terms, haystack)
    if found < min(2, len(terms)):
        return 0.0
    if found < min(3, len(terms)) and not carried_terms(terms, title_text):
        return 0.0
    return found / len(terms)
