"""Exact-phrase pinning of globally unique identifiers in search queries.

[INPUT]
- (none — pure regex transform)

[OUTPUT]
- pin_structured_identifiers: wrap the CVE ids and DOIs that stand outside a quoted phrase in double quotes so engines match them as one literal token

[POS]
Query pre-processor of the web_search toolkit. A CVE id or DOI is a unique identifier whose literal text is its
identity, so tokenizers that split it into fragments only dilute the match; quoting keeps it whole. A phrase the
author already put in double quotes is the author's own exact match and is never rewritten. Entity names such as
tickers are deliberately not pinned: they have many spellings, and quoting one narrows the engine's interpretation
of the query.
"""

from __future__ import annotations

import re

# One pass over the query: each identifier is judged where it stands, so a DOI that is the prefix of another one
# cannot rewrite the other. A double-quoted phrase is matched first and handed back as written (a stray pair of quote
# marks such as inch marks counts as a phrase too). Outside phrases, the lookbehind skips an identifier that is
# already quoted, sits inside a longer word or belongs to a URL path (``doi.org/10.1000/x``,
# ``nvd.nist.gov/vuln/detail/CVE-2024-3094``), where quotes would break the link. The word boundaries are
# ASCII-only because ``\w`` and ``\b`` count CJK characters as word characters, which would leave
# ``分析CVE-2024-3094漏洞`` unpinned.
_PHRASE_OR_IDENTIFIER = re.compile(
    r"""
    "[^"]*"
    |
    (?<![A-Za-z0-9_"'/.])
    (?:
        (?P<cve>CVE-\d{4}-\d{4,7})
      | (?P<doi>10\.\d{4,9}/[-._;()/:A-Za-z0-9]+)
    )
    (?<=[A-Za-z0-9])        # trailing punctuation belongs to the sentence, not to the identifier
    (?![A-Za-z0-9_])
    """,
    re.IGNORECASE | re.VERBOSE,
)


def _pin(match: re.Match[str]) -> str:
    cve = match.group("cve")
    if cve:
        return f'"{cve.upper()}"'
    doi = match.group("doi")
    return f'"{doi}"' if doi else match.group(0)


def pin_structured_identifiers(query: str) -> str:
    """Return ``query`` with every CVE id (upper-cased) and DOI outside a double-quoted phrase wrapped in double quotes.

    A phrase the author already quoted is left as written.
    """
    return _PHRASE_OR_IDENTIFIER.sub(_pin, query)
