"""Visitor language negotiation for the public share pages.

[INPUT]
- starlette.requests::Request (POS: Accept-Language header)
- myrm_agent_harness.utils.locale::is_chinese (POS: single definition of which locale tags count as Chinese)

[OUTPUT]
- ShareLang: languages the share pages are written in
- resolve_share_lang: pick the page language for a request
- HTML_LANG: the ``lang`` attribute of a page written in each language
- SHARE_BRAND: the "shared via" line every share page ends with, in each language

[POS]
Public share links are opened by anonymous recipients, so the conversation, status, password-gate and lockout pages
follow the browser's language instead of the owner's. Chinese and English are shipped; the highest-ranked supported
language in Accept-Language wins and anything else (missing header, ``*``, malformed values, unsupported languages)
reads as English. The two per-language values every page repeats live here so the pages cannot drift apart.
"""

from __future__ import annotations

from typing import Literal

from myrm_agent_harness.utils.locale import is_chinese
from starlette.requests import Request

ShareLang = Literal["en", "zh"]

HTML_LANG: dict[ShareLang, str] = {"en": "en", "zh": "zh-CN"}

SHARE_BRAND: dict[ShareLang, str] = {"en": "Shared via Myrm Agent", "zh": "由 Myrm Agent 分享"}


def _ranked_language_tags(header: str) -> list[str]:
    """Language tags of an Accept-Language value, best first; ``q=0`` and malformed entries are dropped."""
    ranked: list[tuple[float, str]] = []
    for entry in header.split(","):
        tag, _, params = entry.partition(";")
        tag = tag.strip()
        if not tag:
            continue
        quality = 1.0
        params = params.replace(" ", "").lower()
        if params.startswith("q="):
            try:
                quality = float(params[2:])
            except ValueError:
                continue
        if quality > 0:
            ranked.append((quality, tag))
    ranked.sort(key=lambda item: -item[0])
    return [tag for _, tag in ranked]


def resolve_share_lang(request: Request) -> ShareLang:
    """The page language for *request*: the best supported Accept-Language entry, English otherwise."""
    for tag in _ranked_language_tags(request.headers.get("accept-language", "")):
        if is_chinese(tag):
            return "zh"
        if tag.lower().partition("-")[0] == "en":
            return "en"
    return "en"
