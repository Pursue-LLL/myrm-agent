"""[INPUT]
- myrm_agent_harness.toolkits.llms.routing.complexity_router.keywords::_CODE_BLOCK_RE / _INLINE_CODE_RE / _LATEX_BLOCK_RE / _MATH_RE (POS: complexity_router 子包的一部分；由 __init__.py 聚合导出。)

[OUTPUT]
- _score_structural_signals: Score structural signals: URLs, file paths, emails.
- _score_contextual_signals: Score contextual signals: length, image, repetition requests.
- _normalize_query: Extract text from query and detect multimodal media (image/video).
- _has_code_content: _has_code_content
- _has_keywords: _has_keywords
- _has_math_content: _has_math_content
- _is_simple_greeting: _is_simple_greeting
- _word_count: _word_count

[POS]
complexity_router 子包的一部分；由 __init__.py 聚合导出。
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from myrm_agent_harness.toolkits.llms.routing.complexity_router.keywords import (
    _CODE_BLOCK_RE,
    _INLINE_CODE_RE,
    _LATEX_BLOCK_RE,
    _MATH_RE,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


_URL_RE = re.compile(r"https?://\S+")
_FILE_PATH_RE = re.compile(r"(?:/[\w.-]+){2,}|[\w.-]+\.(?:py|js|ts|java|go|rs|cpp|c|h)")


def _score_structural_signals(text: str) -> dict[str, float]:
    """Score structural signals: URLs, file paths, emails.

    Returns dimension scores that feed into unified scoring.
    """
    scores: dict[str, float] = {}

    url_count = len(_URL_RE.findall(text))
    if url_count > 0:
        scores["urls"] = min(url_count * 0.5, 1.5)

    file_count = len(_FILE_PATH_RE.findall(text))
    if file_count > 0:
        scores["file_paths"] = min(file_count * 0.3, 1.0)

    return scores


def _score_contextual_signals(
    text: str,
    has_image: bool,
    word_count: int,
) -> dict[str, float]:
    """Score contextual signals: length, image, repetition requests.

    Returns dimension scores that feed into unified scoring.
    """
    scores: dict[str, float] = {}

    if has_image:
        scores["image_input"] = 6.0  # strong signal — vision models required

    if word_count > 50:
        scores["long_input"] = min((word_count - 50) * 0.02, 0.8)

    repetition_re = re.compile(
        r"(\d{1,6})\s*(?:variations?|options?|alternatives?|versions?|examples?|ways?\s+to)",
        re.IGNORECASE,
    )
    rep_match = repetition_re.search(text)
    if rep_match:
        n = int(rep_match.group(1))
        if n > 9:
            scores["repetition_request"] = 0.9
        elif n > 3:
            scores["repetition_request"] = 0.6
        elif n > 1:
            scores["repetition_request"] = 0.3

    return scores


_MEDIA_TYPES: frozenset[str] = frozenset({"image_url", "image", "video_url"})


def _normalize_query(query: str | list[dict[str, object]]) -> tuple[str, bool]:
    """Extract text from query and detect multimodal media (image/video).

    Video requires vision capability (frame analysis), so it shares the same
    hard floor as images — a video query must never route to the light SIMPLE
    tier, which is not vision-guaranteed.
    """
    if isinstance(query, str):
        return query, False

    text_parts: list[str] = []
    has_image = False
    for item in query:
        if isinstance(item, dict):
            if item.get("type") == "text":
                text_parts.append(str(item.get("text", "")))
            elif item.get("type") in _MEDIA_TYPES:
                has_image = True
    return " ".join(text_parts), has_image


def _has_code_content(text: str) -> bool:
    return bool(_CODE_BLOCK_RE.search(text) or _INLINE_CODE_RE.search(text))


def _has_keywords(text: str, keywords: frozenset[str]) -> bool:
    lower = text.lower()
    return any(kw in lower for kw in keywords)


def _has_math_content(text: str) -> bool:
    return bool(_MATH_RE.search(text) or _LATEX_BLOCK_RE.search(text))


def _is_simple_greeting(text: str, indicators: frozenset[str]) -> bool:
    stripped = text.strip().rstrip("!?！？。.").lower()
    return stripped in indicators


def _word_count(text: str) -> int:
    cjk_chars = len(re.findall(r"[\u4e00-\u9fff\u3400-\u4dbf]", text))
    latin_words = len(re.findall(r"[a-zA-Z]+", text))
    return cjk_chars + latin_words
