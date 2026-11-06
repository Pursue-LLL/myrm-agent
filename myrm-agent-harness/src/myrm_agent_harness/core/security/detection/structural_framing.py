"""Content boundary layers 1 and 1.5 — Unicode homoglyph folding and structural framing strip.

1. **Unicode Folding** — normalizes fullwidth ASCII letters and angle bracket homoglyphs to their ASCII equivalents, so
   a spoofed tag or marker written with look-alikes is found by the same patterns as the real one.
1.5. **Structural Framing Strip** — removes XML role tags, ChatML special tokens, CDATA blocks, and code fences that
   could confuse model role boundaries. Only targets a strict whitelist of known framing tokens, fullwidth look-alikes
   of them included. A cut can splice the text around it into a new tag, so the cut repeats while tags are left; after
   a bounded number of rounds the remainder is replaced by a placeholder.

[INPUT]
- (none — self-contained, pure standard library)

[OUTPUT]
- fold_unicode(): Unicode homoglyph folding (layer 1)
- strip_structural_framing(): structural framing token strip (layer 1.5)
- replace_spans(): replace character spans of a text with a fixed string
- PLACEHOLDER: the text that stands in for what the strip cannot cut

[POS]
Normalization stage of the content boundary defense, consumed by `content_boundary.sanitize`.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Layer 1: Unicode homoglyph folding
# ---------------------------------------------------------------------------

_FULLWIDTH_ASCII_OFFSET = 0xFEE0

_ANGLE_BRACKET_MAP: dict[int, str] = {
    0xFF1C: "<",  # fullwidth <
    0xFF1E: ">",  # fullwidth >
    0x2329: "<",  # left-pointing angle bracket
    0x232A: ">",  # right-pointing angle bracket
    0x3008: "<",  # CJK left angle bracket
    0x3009: ">",  # CJK right angle bracket
    0x2039: "<",  # single left-pointing angle quotation mark
    0x203A: ">",  # single right-pointing angle quotation mark
    0x27E8: "<",  # mathematical left angle bracket
    0x27E9: ">",  # mathematical right angle bracket
    0xFE64: "<",  # small less-than sign
    0xFE65: ">",  # small greater-than sign
    0x00AB: "<",  # left-pointing double angle quotation mark
    0x00BB: ">",  # right-pointing double angle quotation mark
    0x300A: "<",  # left double angle bracket
    0x300B: ">",  # right double angle bracket
    0x27EA: "<",  # mathematical left double angle bracket
    0x27EB: ">",  # mathematical right double angle bracket
    0x27EC: "<",  # mathematical left white tortoise shell bracket
    0x27ED: ">",  # mathematical right white tortoise shell bracket
    0x27EE: "<",  # mathematical left flattened parenthesis
    0x27EF: ">",  # mathematical right flattened parenthesis
    0x276C: "<",  # medium left-pointing angle bracket ornament
    0x276D: ">",  # medium right-pointing angle bracket ornament
    0x276E: "<",  # heavy left-pointing angle quotation mark ornament
    0x276F: ">",  # heavy right-pointing angle quotation mark ornament
    0x02C2: "<",  # modifier letter left arrowhead
    0x02C3: ">",  # modifier letter right arrowhead
}

_HOMOGLYPH_RE = re.compile(
    r"[\uFF21-\uFF3A\uFF41-\uFF5A\uFF1C\uFF1E"
    r"\u2329\u232A\u3008\u3009\u2039\u203A"
    r"\u27E8-\u27EF\uFE64\uFE65\u00AB\u00BB"
    r"\u300A\u300B\u276C-\u276F\u02C2\u02C3]"
)


def _fold_char(char: str) -> str:
    code = ord(char)
    if 0xFF21 <= code <= 0xFF3A or 0xFF41 <= code <= 0xFF5A:
        return chr(code - _FULLWIDTH_ASCII_OFFSET)
    bracket = _ANGLE_BRACKET_MAP.get(code)
    return bracket if bracket else char


def fold_unicode(text: str) -> str:
    """Normalize Unicode homoglyphs to ASCII equivalents."""
    return _HOMOGLYPH_RE.sub(lambda m: _fold_char(m.group()), text)


# ---------------------------------------------------------------------------
# Layer 1.5: Structural framing token stripping
# ---------------------------------------------------------------------------

_STRUCTURAL_FRAMING_RE = re.compile(
    r"</?(?:tool_call|function_call|result|response|output|input|system|assistant|user"
    r"|skills_sop|skill_entry|data_boundary_rules|user_instructions|workspace_context|user_memory_context|bound_skills"
    r"|system_notification|graph_patch|verification_evidence|handover|preserve_context|pre_compact_recall_context"
    r"|sandbox_environment_snapshot|untrusted_objective)(?:[\s/][^>]*)?>"
    r"|<\|(?:im_start|im_end|endoftext)\|>"
    r"|<!\[CDATA\[.*?\]\]>"
    r"|^\s*```(?:json|xml|html|markdown|python|bash|sh|javascript|typescript)?\s*$"
    r"|^\s*```\s*$",
    re.IGNORECASE | re.DOTALL | re.MULTILINE,
)


PLACEHOLDER = "[[SANITIZED]]"

# Every cut is a full pass over the text. Honest text needs one; input that still splices a tag back together after
# this many is built to defeat the strip, and cutting on would cost quadratic time.
_MAX_FRAMING_CUTS = 3


def replace_spans(text: str, spans: list[tuple[int, int]], replacement: str) -> str:
    """``text`` with every ``(start, end)`` span replaced by ``replacement``."""
    if not spans:
        return text
    parts: list[str] = []
    cursor = 0
    for start, end in spans:
        parts.append(text[cursor:start])
        parts.append(replacement)
        cursor = end
    parts.append(text[cursor:])
    return "".join(parts)


# Fullwidth letters and ＜ ＞ are exact look-alikes of the tag they imitate. The typographic brackets that
# ``_HOMOGLYPH_RE`` also covers («», 《》) are ordinary quotes around words like «system», so tag matching leaves them be.
_FULLWIDTH_TAG_RE = re.compile(r"[\uFF21-\uFF3A\uFF41-\uFF5A\uFF1C\uFF1E]")


def _framing_spans(text: str) -> list[tuple[int, int]]:
    """Spans of structural framing tokens in ``text``, fullwidth look-alikes (``＜/user_memory_context＞``) included.

    Folding keeps the length, so spans found on the folded text apply to ``text`` itself.
    """
    folded = _FULLWIDTH_TAG_RE.sub(lambda m: _fold_char(m.group()), text)
    return [m.span() for m in _STRUCTURAL_FRAMING_RE.finditer(folded)]


def strip_structural_framing(text: str) -> str:
    """Remove structural framing tokens that could confuse model role boundaries.

    Strips XML role tags, ChatML special tokens, CDATA blocks, and code fences.
    Only targets a strict whitelist — unrelated XML tags are preserved.

    Cutting a tag can splice its neighbours into a new one (``</user_memo<system>ry_context>``), so the cut is
    repeated while tags are left. After ``_MAX_FRAMING_CUTS`` rounds what is still there is replaced by a placeholder
    instead, which ends the loop in a bounded number of passes. The placeholder cannot join its neighbours into a role
    tag, a frame tag or a ChatML token; it can only complete the CDATA delimiters (``<![CDATA[`` ... ``]]>``), which
    mean nothing to the model.
    """
    for _ in range(_MAX_FRAMING_CUTS):
        spans = _framing_spans(text)
        if not spans:
            return text
        text = replace_spans(text, spans, "")
    return replace_spans(text, _framing_spans(text), PLACEHOLDER)
