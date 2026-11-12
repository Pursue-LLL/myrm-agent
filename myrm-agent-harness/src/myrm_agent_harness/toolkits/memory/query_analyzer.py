"""Query analysis for memory retrieval boosting.

Detects special patterns in queries to apply targeted scoring boosts:
- Quoted phrases: "exact match" → boost memories containing this phrase
- Person names: proper nouns → boost memories mentioning these entities
- Temporal markers: "yesterday", "last week" → proximity scoring around the
  anchor of the window resolved by ``_internal.temporal_window``

[POS]
Query pattern recognition utilities for hybrid memory scoring enhancement.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from myrm_agent_harness.toolkits.memory._internal.temporal_window import derive_temporal_window


@dataclass
class QueryContext:
    """Parsed query context for targeted retrieval.

    ``temporal_markers`` holds the marker the shared temporal rules matched
    (empty when none) and ``reference_time`` the proximity anchor of its
    window, so the soft boost and the collect-stage hard filter agree on
    which period the query means.
    """

    quoted_phrases: list[str]
    person_names: list[str]
    temporal_markers: list[str]
    reference_time: datetime | None = None
    is_preference_query: bool = False


def analyze_query(query: str, *, now: datetime | None = None) -> QueryContext:
    """Analyze query for special patterns.

    Args:
        query: Retrieval query text.
        now: Reference instant for relative time phrases; defaults to UTC now.

    Returns:
        QueryContext with extracted patterns
    """
    quoted_phrases = extract_quoted_phrases(query)
    person_names = extract_person_names(query)
    window = derive_temporal_window(query, now=now)
    is_pref_query = is_preference_query(query)

    return QueryContext(
        quoted_phrases=quoted_phrases,
        person_names=person_names,
        temporal_markers=[window.marker] if window else [],
        reference_time=window.anchor if window else None,
        is_preference_query=is_pref_query,
    )


def extract_quoted_phrases(query: str) -> list[str]:
    """Extract quoted phrases from query.

    Examples:
        "I said 'hello world'" → ["hello world"]
        'She told me "do it now"' → ["do it now"]
    """
    patterns = [
        r'"([^"]+)"',
        r"'([^']+)'",
        r"「([^」]+)」",
    ]

    phrases: list[str] = []
    for pattern in patterns:
        phrases.extend(re.findall(pattern, query))

    return [p.strip() for p in phrases if len(p.strip()) > 2]


def extract_person_names(query: str) -> list[str]:
    """Extract potential person names (simplified proper noun detection).

    Heuristic: capitalized words not at sentence start, not common words.

    Examples:
        "Ask John about this" → ["John"]
        "Tell Mary and Bob" → ["Mary", "Bob"]
    """
    common_words = {
        "I",
        "We",
        "You",
        "They",
        "He",
        "She",
        "It",
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    }

    words = query.split()
    names: list[str] = []

    for i, word in enumerate(words):
        word_clean = word.strip(",.!?;:")
        if not word_clean or len(word_clean) < 2:
            continue

        if word_clean[0].isupper() and word_clean.isalpha():
            if i == 0:
                continue
            if word_clean not in common_words:
                names.append(word_clean)

    return names


def contains_quoted_phrase(content: str, phrase: str) -> bool:
    """Check if content contains the quoted phrase (case-insensitive).

    Args:
        content: Memory content to search
        phrase: Quoted phrase to find

    Returns:
        True if phrase is found in content
    """
    return phrase.lower() in content.lower()


def contains_person_name(content: str, name: str) -> bool:
    """Check if content mentions the person name.

    Args:
        content: Memory content to search
        name: Person name to find

    Returns:
        True if name is found in content (word boundary match)
    """
    pattern = rf"\b{re.escape(name)}\b"
    return bool(re.search(pattern, content, re.IGNORECASE))


# Assistant-reference query detection
ASSISTANT_REF_TRIGGERS = [
    r"\byou suggested\b",
    r"\byou told me\b",
    r"\byou mentioned\b",
    r"\byou recommended\b",
    r"\bremind me what you\b",
    r"\byou provided\b",
    r"\byou listed\b",
    r"\byou gave me\b",
    r"\byou described\b",
    r"\bwhat did you\b",
    r"\byou came up with\b",
    r"\byou helped me\b",
    r"\byou explained\b",
    r"\bcan you remind me\b",
    r"\byou identified\b",
    r"\byou said\b",
    r"你建议",
    r"你说过",
    r"你之前提到",
    r"你提到的",
    r"你帮我",
    r"你推荐",
    r"你给我",
    r"你解释",
    r"你说的",
    r"你提供的",
    r"你列的",
    r"提醒我你",
]


# Preference query detection
PREFERENCE_QUERY_TRIGGERS = [
    r"\bwhat (?:do|did) i (?:like|love|enjoy|prefer)\b",
    r"\bmy (?:favorite|preference)\b",
    r"\bwhat (?:do|did) i usually\b",
    r"\bwhat (?:am|was) i interested in\b",
    r"\bwhat (?:do|did) i dislike\b",
    r"\bwhat (?:do|did) i hate\b",
    r"\bwhat (?:do|did) i want\b",
    r"\bwhat (?:do|did) i need\b",
    r"\bwhat (?:have|had) i been (?:working on|focused on|interested in|struggling with|worried about)\b",
    r"\bremind me (?:what|about) i (?:like|prefer|enjoy|want)\b",
    r"\bmy habit\b",
    r"\bmy belief\b",
    r"\bmy goal\b",
    r"我喜欢什么",
    r"我的偏好",
    r"我通常",
    r"我习惯",
    r"我想要",
    r"我倾向",
    r"我的习惯",
    r"我的目标",
    r"我喜欢用",
    r"我偏好",
    r"我讨厌",
    r"我不喜欢",
]


def is_preference_query(query: str) -> bool:
    """Detect if query is asking about user preferences or habits.

    Preference queries ask about what the user likes/prefers/enjoys,
    like "What do I like?" or "My favorite X?" or "What am I interested in?".

    These queries benefit from preference boost on semantic memories that
    have been tagged with preference_type and preference_strength.

    Args:
        query: User query text

    Returns:
        True if query is asking about preferences

    Examples:
        >>> is_preference_query("What do I like for breakfast?")
        True
        >>> is_preference_query("My favorite color?")
        True
        >>> is_preference_query("Tell me about Python")
        False
    """
    query_lower = query.lower()
    return any(re.search(trigger, query_lower) for trigger in PREFERENCE_QUERY_TRIGGERS)


def is_assistant_reference_query(query: str) -> bool:
    """Detect if query is asking about assistant's previous responses.

    Assistant-reference queries ask about what the AI said/suggested/explained,
    like "What did you recommend?" or "You told me X, remind me?".

    These queries need special handling (Two-Pass retrieval) because standard
    search only indexes user turns, missing assistant responses.

    Args:
        query: User query text

    Returns:
        True if query refers to assistant's previous responses

    Examples:
        >>> is_assistant_reference_query("What did you suggest for X?")
        True
        >>> is_assistant_reference_query("Tell me about Y")
        False
    """
    query_lower = query.lower()
    return any(re.search(trigger, query_lower) for trigger in ASSISTANT_REF_TRIGGERS)
