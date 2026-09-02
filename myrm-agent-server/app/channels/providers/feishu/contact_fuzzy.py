"""Feishu contact fuzzy matcher and disambiguation engine.

[INPUT]
- Contact user records (dict containing open_id, name, department, avatar, etc.)
- Search query text (e.g. "张廷", "wangwei", "李伟")

[OUTPUT]
- ContactMatchResult: structured match result containing matched candidates and disambiguation flag

[POS]
Pure standard library fuzzy matching engine for enterprise contacts.
Supports Pinyin-tolerant matching, Levenshtein distance, department weighting,
and confidence threshold-based disambiguation.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from typing import Final

# Common Chinese homophones/near-homophones mapping for contact name resilience
_HOMOPHONE_MAP: Final[dict[str, str]] = {
    "廷": "ting",
    "婷": "ting",
    "霆": "ting",
    "婷婷": "tingting",
    "伟": "wei",
    "玮": "wei",
    "炜": "wei",
    "薇": "wei",
    "磊": "lei",
    "蕾": "lei",
    "强": "qiang",
    "翔": "xiang",
    "祥": "xiang",
    "宇": "yu",
    "雨": "yu",
    "羽": "yu",
    "洋": "yang",
    "阳": "yang",
    "静": "jing",
    "婧": "jing",
    "敬": "jing",
    "文": "wen",
    "雯": "wen",
    "明": "ming",
    "敏": "min",
    "华": "hua",
    "桦": "hua",
    "峰": "feng",
    "锋": "feng",
}

# Confidence thresholds
CONFIDENCE_AUTO_ACCEPT: Final[float] = 0.85
CONFIDENCE_MIN_CANDIDATE: Final[float] = 0.40
DISAMBIGUATION_DIFF_THRESHOLD: Final[float] = 0.15


@dataclass(frozen=True)
class ContactCandidate:
    """Individual matched contact candidate."""

    open_id: str
    name: str
    department: str = ""
    email: str = ""
    avatar_url: str = ""
    score: float = 0.0


@dataclass
class ContactMatchResult:
    """Structured result of contact fuzzy matching."""

    query: str
    best_match: ContactCandidate | None = None
    candidates: list[ContactCandidate] = field(default_factory=list)
    requires_disambiguation: bool = False
    is_confident_match: bool = False


def _normalize_token(text: str) -> str:
    """Normalize text by stripping whitespace, symbols, and lowercasing."""
    if not text:
        return ""
    # Strip common titles / prefixes
    text = re.sub(r"[，。！？,\.!\s\(\)（）]", "", text)
    return text.strip().lower()


def _approximate_pinyin_signature(name: str) -> str:
    """Generate approximate phonetic signature using homophone map."""
    chars: list[str] = []
    for char in name:
        if char in _HOMOPHONE_MAP:
            chars.append(_HOMOPHONE_MAP[char])
        else:
            chars.append(char.lower())
    return "".join(chars)


def calculate_name_similarity(query: str, target_name: str) -> float:
    """Calculate phonetic and character similarity between query and candidate name.

    Returns float in range [0.0, 1.0].
    """
    q_norm = _normalize_token(query)
    t_norm = _normalize_token(target_name)

    if not q_norm or not t_norm:
        return 0.0

    # 1. Exact match (case-insensitive)
    if q_norm == t_norm:
        return 1.0

    # 2. Substring inclusion
    if q_norm in t_norm:
        # Penalize if query is much shorter than target
        ratio = len(q_norm) / len(t_norm)
        return min(0.95, 0.70 + 0.25 * ratio)

    if t_norm in q_norm:
        ratio = len(t_norm) / len(q_norm)
        return min(0.90, 0.65 + 0.25 * ratio)

    # 3. Direct character SequenceMatcher similarity
    char_sim = difflib.SequenceMatcher(None, q_norm, t_norm).ratio()

    # 4. Phonetic / homophone signature similarity
    q_sig = _approximate_pinyin_signature(q_norm)
    t_sig = _approximate_pinyin_signature(t_norm)
    phonetic_sim = difflib.SequenceMatcher(None, q_sig, t_sig).ratio()

    # Weight character and phonetic similarity
    combined_score = max(char_sim, phonetic_sim * 0.95, (char_sim + phonetic_sim) / 2.0)
    return round(combined_score, 4)


class FeishuContactFuzzyMatcher:
    """Enterprise contact fuzzy matching and disambiguation engine."""

    def __init__(self, contacts: list[dict[str, object]] | None = None) -> None:
        """Initialize matcher with optional preloaded contact directory.

        Args:
            contacts: List of contact dicts containing open_id, name, department_name, etc.
        """
        self._contacts: list[dict[str, object]] = contacts or []

    def update_contacts(self, contacts: list[dict[str, object]]) -> None:
        """Update cached contact directory."""
        self._contacts = contacts

    def match(
        self,
        query: str,
        *,
        limit: int = 5,
        department_hint: str = "",
    ) -> ContactMatchResult:
        """Fuzzy match query against contact directory with disambiguation guardrails.

        Args:
            query: Target person name (e.g. "张廷", "王伟")
            limit: Maximum candidates to return
            department_hint: Optional department name hint to boost relevant candidates

        Returns:
            ContactMatchResult with best match or disambiguation requirements
        """
        query_norm = _normalize_token(query)
        if not query_norm or not self._contacts:
            return ContactMatchResult(query=query)

        scored_candidates: list[ContactCandidate] = []
        dep_hint_norm = _normalize_token(department_hint)

        for contact in self._contacts:
            open_id = str(contact.get("open_id") or contact.get("user_id") or "")
            name = str(contact.get("name") or "")
            dept = str(contact.get("department_name") or contact.get("department") or "")
            email = str(contact.get("email") or "")
            avatar = str(contact.get("avatar_url") or "")

            if not open_id or not name:
                continue

            base_score = calculate_name_similarity(query_norm, name)

            # Department hint boost (+0.20 for matching, penalty for non-matching if hint present)
            if dep_hint_norm:
                if dept and dep_hint_norm in dept.lower():
                    base_score = min(1.0, base_score + 0.15)
                else:
                    base_score = max(0.0, base_score - 0.15)

            if base_score >= CONFIDENCE_MIN_CANDIDATE:
                candidate = ContactCandidate(
                    open_id=open_id,
                    name=name,
                    department=dept,
                    email=email,
                    avatar_url=avatar,
                    score=base_score,
                )
                scored_candidates.append(candidate)

        # Sort descending by score
        scored_candidates.sort(key=lambda c: c.score, reverse=True)
        top_candidates = scored_candidates[:limit]

        if not top_candidates:
            return ContactMatchResult(query=query)

        best = top_candidates[0]

        # Determine if disambiguation is required
        requires_disambiguation = False
        is_confident = False

        if len(top_candidates) == 1:
            if best.score >= CONFIDENCE_AUTO_ACCEPT:
                is_confident = True
        else:
            second = top_candidates[1]
            score_diff = best.score - second.score

            if best.score >= CONFIDENCE_AUTO_ACCEPT and score_diff >= DISAMBIGUATION_DIFF_THRESHOLD:
                is_confident = True
            else:
                # Multiple close candidates -> require user disambiguation
                requires_disambiguation = True

        return ContactMatchResult(
            query=query,
            best_match=best if is_confident else None,
            candidates=top_candidates,
            requires_disambiguation=requires_disambiguation,
            is_confident_match=is_confident,
        )
