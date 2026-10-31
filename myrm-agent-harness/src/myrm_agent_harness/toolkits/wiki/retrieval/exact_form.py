"""Exact-form-first ordering of full-text candidates.

[INPUT]
- .tokenizer::extract_query_terms (POS: normalized query terms shared with index routing)

[OUTPUT]
- MAX_REORDERED_ROWS: the most rows one search reads page text for and orders; a longer window keeps the order of the match
- exact_form_terms: the plain English words of a query, the terms whose spelling a page can match or miss
- rank_exact_forms_first: candidates reordered so a page that spells more of those words exactly comes first

[POS]
Re-ranking step after the FTS5 match and before the fusion and seeding that consume it. The wiki tables stem
English words, so bm25 scores `transformer` and `Transformers` as the same term and a page that spells the
query exactly ranks no better than one that only shares the stem. This step puts the exact spelling first and
keeps the bm25 order among pages that spell the same number of query words; a query without a plain English
word (a Chinese query, say) is left in the order bm25 gave it.
"""

from __future__ import annotations

import re

from .tokenizer import extract_query_terms

_WORD_RE = re.compile(r"[a-z0-9]+")

# Reading and splitting the text of a page costs about 0.2 ms, so a search that asks for a long window of rows
# (a deep page of results) is not reordered, which bounds the work and the memory of one search.
MAX_REORDERED_ROWS = 300


def exact_form_terms(query: str) -> frozenset[str]:
    """Lower-cased letters-and-digits words of ``query`` (CJK tokens, and terms such as ``c++``, are left out)."""
    return frozenset(term for term in extract_query_terms(query) if term.isascii() and term.isalnum())


def rank_exact_forms_first(candidates: list[tuple[str, float, str]], terms: frozenset[str]) -> list[tuple[str, float]]:
    """Order ``(name, score, text)`` candidates by how many ``terms`` their text spells as whole words, then by score.

    The scores are handed out again in descending order, so the best score belongs to the first candidate: a
    caller that sorts by score keeps this order, and the set of scores, which other seeds are weighed against,
    does not change.
    """
    if not terms or len(candidates) < 2:
        return [(name, score) for name, score, _ in candidates]
    spelled = [len(terms & set(_WORD_RE.findall(text.lower()))) for _, _, text in candidates]
    order = sorted(range(len(candidates)), key=lambda i: (-spelled[i], -candidates[i][1]))
    scores = sorted((score for _, score, _ in candidates), reverse=True)
    return [(candidates[i][0], score) for i, score in zip(order, scores, strict=True)]
