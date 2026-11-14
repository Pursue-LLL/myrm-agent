"""Progressive fuzzy matching for text replacement.

8-strategy chain (+ Unicode preprocessing) for LLM-generated code variations:
exact → line_trimmed → whitespace_normalized → indent_flexible →
escape_normalized → trimmed_boundary → block_anchored → context_aware.
Includes escape-drift detection.

[INPUT]
- utils._fuzzy_strategies::STRATEGIES, normalize_unicode, needs_unicode_normalization (POS: The strategy chain and the Unicode preprocessing)

[POS]
Generic fuzzy matching module. Public API of the 8-strategy progressive chain (+Unicode
preprocessing + escape-drift detection).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from ._fuzzy_strategies import STRATEGIES, needs_unicode_normalization, normalize_unicode

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FuzzyMatchResult:
    """Result of a successful fuzzy find."""

    matched_text: str
    strategy: str
    confidence: float


@dataclass(frozen=True)
class FuzzyReplaceResult:
    """Result of a fuzzy replace operation."""

    content: str
    strategy: str
    success: bool
    confidence: float


# Strategies at or above this confidence match the fragment's own text apart from whitespace, indentation, escapes and
# blank edge lines. Below it, block_anchored and context_aware anchor on the first and last line and let the lines in
# between differ, so an edit built on them replaces real lines with the caller's guess. Edits that overwrite file
# content pass this as `min_confidence`.
CONTENT_PRESERVING_MIN_CONFIDENCE = 0.75

_ESCAPE_DRIFT_RE = re.compile(r"""\\['"]""")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def fuzzy_find(content: str, fragment: str, *, min_confidence: float = 0.0) -> FuzzyMatchResult | None:
    """Find a text fragment in content using progressive strategies.

    Tries each strategy in order (cheapest first). Returns the first
    successful match, or None if no strategy succeeds. Strategies whose
    confidence is below ``min_confidence`` are not tried.
    """
    if not content or not fragment:
        return None

    search_content = content
    search_fragment = fragment
    if needs_unicode_normalization(fragment) or needs_unicode_normalization(content):
        search_content = normalize_unicode(content)
        search_fragment = normalize_unicode(fragment)

    for name, finder, confidence in STRATEGIES:
        if confidence < min_confidence:
            continue
        matched = finder(search_content, search_fragment)
        if matched is None:
            continue

        if search_content != content:
            original_matched = _recover_original_text(content, search_content, matched)
            if original_matched is None:
                continue
            matched = original_matched

        logger.debug("fuzzy_find: strategy=%s confidence=%.2f", name, confidence)
        return FuzzyMatchResult(
            matched_text=matched,
            strategy=name,
            confidence=confidence,
        )

    return None


def fuzzy_replace(
    content: str,
    old_fragment: str,
    new_fragment: str,
    *,
    replace_all: bool = False,
    min_confidence: float = 0.0,
) -> FuzzyReplaceResult:
    """Find and replace a text fragment using progressive fuzzy matching.

    Returns FuzzyReplaceResult with success=False if no match found.
    ``min_confidence`` is passed to ``fuzzy_find``.
    """
    if not content or not old_fragment:
        return FuzzyReplaceResult(content=content, strategy="none", success=False, confidence=0.0)

    result = fuzzy_find(content, old_fragment, min_confidence=min_confidence)
    if result is None:
        return FuzzyReplaceResult(content=content, strategy="none", success=False, confidence=0.0)

    matched = result.matched_text
    count = content.count(matched)

    if count == 0:
        # The line strategies rejoin the lines they match with ``\n``, so content that separates its lines otherwise
        # (CR, FF, U+2028) does not hold the text they matched; replacing nothing must not read as a success.
        return FuzzyReplaceResult(content=content, strategy=result.strategy, success=False, confidence=0.0)

    if not replace_all and count > 1:
        logger.warning(
            "fuzzy_replace: multi-match rejected strategy=%s count=%d",
            result.strategy,
            count,
        )
        return FuzzyReplaceResult(content=content, strategy=result.strategy, success=False, confidence=0.0)

    if result.strategy != "exact":
        drift_err = _detect_escape_drift(matched, new_fragment)
        if drift_err:
            logger.warning("fuzzy_replace: escape drift blocked — %s", drift_err)
            return FuzzyReplaceResult(content=content, strategy=result.strategy, success=False, confidence=0.0)

    if replace_all:
        new_content = content.replace(matched, new_fragment)
    else:
        new_content = content.replace(matched, new_fragment, 1)

    logger.debug(
        "fuzzy_replace: strategy=%s confidence=%.2f replace_all=%s",
        result.strategy,
        result.confidence,
        replace_all,
    )
    return FuzzyReplaceResult(
        content=new_content,
        strategy=result.strategy,
        success=True,
        confidence=result.confidence,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _detect_escape_drift(
    matched_region: str,
    new_fragment: str,
) -> str | None:
    """Detect tool-call serialization escape drift (\\' or \\") in new_fragment."""
    has_escapes_in_new = bool(_ESCAPE_DRIFT_RE.search(new_fragment))
    has_escapes_in_old = bool(_ESCAPE_DRIFT_RE.search(matched_region))
    if has_escapes_in_new and not has_escapes_in_old:
        return (
            "Escape-drift detected: new_str contains backslash-escaped quotes "
            "(\\' or \\\") but the matched region does not. This is likely "
            "tool-call serialization corruption. Please re-read the file and retry."
        )
    return None


def _recover_original_text(
    original_content: str,
    normalized_content: str,
    normalized_match: str,
) -> str | None:
    """Map a match in normalized content back to the same line range in original."""
    norm_lines = normalized_content.splitlines()
    match_lines = normalized_match.splitlines()
    match_len = len(match_lines)
    if match_len == 0:
        return None

    orig_lines = original_content.splitlines()
    if len(orig_lines) != len(norm_lines):
        return None

    for i in range(len(norm_lines) - match_len + 1):
        if norm_lines[i : i + match_len] == match_lines:
            return "\n".join(orig_lines[i : i + match_len])
    return None
