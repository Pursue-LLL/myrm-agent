"""Unified locale normalization for harness modules.

[INPUT]
- (none — leaf module)

[OUTPUT]
- LocaleResolver: BCP-47 normalization (Chinese resolves to zh-CN or zh-TW) and Chinese-family detection

[POS]
Shared locale utilities consumed by channel i18n, error diagnostics, and
component text fallbacks. Single source of truth for locale string handling.
Chinese is a family: prompt and tool text branch on is_chinese, while text catalogs pick a
bundle by the exact locale and let zh-TW fall back to zh-CN.
"""

from __future__ import annotations

import os
from itertools import takewhile
from typing import Final

DEFAULT_LOCALE: Final[str] = "en"

# Chinese-first IM platforms when no user preference is available.
PLATFORM_DEFAULT_LOCALES: Final[dict[str, str]] = {
    "feishu": "zh-CN",
    "dingtalk": "zh-CN",
    "wechat": "zh-CN",
    "wecom": "zh-CN",
    "wechat_official": "zh-CN",
    "qq": "zh-CN",
}

# Regions whose Chinese is written in the Traditional script when the tag carries no script subtag.
_TRADITIONAL_REGIONS: Final[frozenset[str]] = frozenset({"tw", "hk", "mo"})


def _names_traditional_chinese(tag: str) -> bool:
    """Whether a lowercase ``zh`` tag names Traditional Chinese: the script subtag decides, otherwise the region does."""
    # A singleton opens extension or private-use subtags, which never name the script or region.
    subtags = list(takewhile(lambda subtag: len(subtag) > 1, tag.split(".")[0].split("-")[1:]))
    for subtag in subtags:
        if len(subtag) == 4 and subtag.isalpha():
            return subtag == "hant"
    return not _TRADITIONAL_REGIONS.isdisjoint(subtags)


def normalize_locale(value: str | None) -> str:
    """Normalize a locale string.

    Chinese resolves to ``zh-TW`` when the tag names Traditional Chinese and to ``zh-CN`` otherwise; C/POSIX
    resolves to en; everything else passes through.
    """
    if not value or not str(value).strip():
        return DEFAULT_LOCALE

    raw = str(value).strip().replace("_", "-")
    lower = raw.lower()

    if lower in {"c", "posix"}:
        return DEFAULT_LOCALE

    if lower.startswith("zh"):
        return "zh-TW" if _names_traditional_chinese(lower) else "zh-CN"

    return raw


def resolve_locale(
    *,
    explicit: str | None = None,
    metadata_locale: str | None = None,
    platform_locale: str | None = None,
    user_locale: str | None = None,
    channel: str | None = None,
) -> str:
    """Resolve locale using priority: explicit > metadata > platform > user > platform-default > en."""
    for candidate in (explicit, metadata_locale, platform_locale, user_locale):
        if candidate:
            return normalize_locale(candidate)

    if channel:
        platform_default = PLATFORM_DEFAULT_LOCALES.get(channel.lower())
        if platform_default:
            return normalize_locale(platform_default)

    env_locale = os.environ.get("MYRM_LOCALE")
    if env_locale:
        return normalize_locale(env_locale)

    return DEFAULT_LOCALE


def is_chinese(locale: str | None) -> bool:
    """Return True when locale resolves to Chinese, Simplified or Traditional."""
    return normalize_locale(locale).startswith("zh")
