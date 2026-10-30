"""FTS5 tokenization for wiki search: the tokenizer every wiki FTS5 table is created with and the query builder.

[INPUT]
- re (POS: standard library regex)

[OUTPUT]
- FTS_TOKENIZER: tokenizer of every wiki FTS5 table (English words are stemmed when indexed and when queried)
- tokenize_for_fts: Build FTS5 query with CJK bigram support
- extract_query_terms: Normalized query term set for index routing and keyword overlap
- STOP_WORDS: English + Chinese stop words for FTS filtering

[POS]
Tokenization utilities for FTS5 full-text search, including CJK (Chinese/Japanese/Korean)
bigram splitting and multi-language stop word filtering. The table tokenizer and the query
builder live together because a query term is tokenized by the table it is matched against.
"""

from __future__ import annotations

import re

from myrm_agent_harness.toolkits.retriever.cjk_tokenizer import tokenize_cjk_bigram

STOP_WORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "but",
        "by",
        "for",
        "if",
        "in",
        "into",
        "is",
        "it",
        "no",
        "not",
        "of",
        "on",
        "or",
        "such",
        "that",
        "the",
        "their",
        "then",
        "there",
        "these",
        "they",
        "this",
        "to",
        "was",
        "will",
        "with",
        "what",
        "how",
        "why",
        "who",
        "where",
        "when",
        "does",
        "do",
        "did",
        "can",
        "could",
        "should",
        "would",
        "的",
        "了",
        "和",
        "是",
        "就",
        "都",
        "而",
        "及",
        "与",
        "着",
        "或",
        "一个",
        "没有",
        "我们",
        "你们",
        "他们",
        "它",
        "它们",
        "什么",
        "怎么",
        "如何",
        "为什么",
        "谁",
        "在哪",
        "何时",
    }
)

CJK_RE = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf\uF900-\uFAFF]+")

# ``porter`` reduces an English word to its stem and ``tokenize_for_fts`` quotes every query term, so the
# table stems the query term the same way: `transformer` matches a page that says `Transformers`. It leaves
# a CJK token as it is (CJK text is segmented into the ``search_terms`` column before it is indexed).
FTS_TOKENIZER = "porter unicode61 remove_diacritics 1"


def tokenize_for_fts(query: str) -> str:
    """Build FTS5 query with CJK bigram and unigram support for proper search."""
    tokens = tokenize_cjk_bigram(query)
    fts_tokens: list[str] = []
    for token in tokens:
        if token.lower() not in STOP_WORDS and token.strip():
            fts_tokens.append(f'"{token}"')

    return " ".join(fts_tokens)


def extract_query_terms(query: str) -> set[str]:
    """Extract normalized terms for index routing and keyword overlap (EN + CJK unigram + bigrams)."""
    tokens = tokenize_cjk_bigram(query)
    terms: set[str] = set()
    for token in tokens:
        term = token.lower().strip()
        if term and term not in STOP_WORDS:
            terms.add(term)
    return terms
