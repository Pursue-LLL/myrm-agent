"""Diagnostic copy reaches end users verbatim, so it names no configuration identifier.

The web error card and the trusted-owner channel reply show ``user_message`` and ``resolution_steps`` as they are in the
bundled catalogs. An end user cannot act on ``base_url``, ``LLMConfig`` or ``MYRM_TLS_STRICT``: a step either points at
something in the product's settings or it is not a step. The check covers every error type in every shipped locale, so a
new catalog entry cannot bring an identifier back.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from pathlib import Path

import pytest

from myrm_agent_harness.agent.errors.diagnostics.i18n import manager as manager_module

_LOCALES = ("en", "zh-CN", "zh-TW", "ja", "ko", "de")
_LOCALES_DIR = Path(manager_module.__file__).parent / "locales"
_COPY_SUFFIXES = ("_user_message", "_resolution_steps", "_wait_step")

# ASCII-only boundaries: ja/zh text puts an identifier right next to CJK characters.
_SNAKE_CASE = re.compile(r"(?<![A-Za-z0-9_])[A-Za-z0-9]+(?:_[A-Za-z0-9]+)+(?![A-Za-z0-9_])")
_CONFIG_CLASS = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]*Config(?![A-Za-z0-9])")
_PLACEHOLDER = re.compile(r"\{[^{}]*\}")
_LIBRARY_WORDS = ("litellm", "debug", "调试", "調試", "除錯", "偵錯", "デバッグ", "디버그")


def _copy_lines(locale: str) -> Iterator[tuple[str, str]]:
    bundle: dict[str, str | list[str]] = json.loads((_LOCALES_DIR / f"{locale}.json").read_text(encoding="utf-8"))
    for key, value in bundle.items():
        if not key.endswith(_COPY_SUFFIXES):
            continue
        for index, text in enumerate(value if isinstance(value, list) else [value]):
            yield f"{key}[{index}]", text


def _identifiers(text: str) -> list[str]:
    # A placeholder such as {base_url_display} is filled with the user's own value at render time.
    visible = _PLACEHOLDER.sub("", text)
    found = _SNAKE_CASE.findall(visible) + _CONFIG_CLASS.findall(visible)
    return found + [word for word in _LIBRARY_WORDS if word in visible.lower()]


@pytest.mark.parametrize("locale", _LOCALES)
def test_catalog_copy_names_no_configuration_identifier(locale: str) -> None:
    offenders = [f"{where}: {text}" for where, text in _copy_lines(locale) if _identifiers(text)]

    assert offenders == []


def test_the_scan_sees_identifiers_next_to_cjk_text_and_ignores_placeholders() -> None:
    assert _identifiers("LLMConfigのbase_url設定を確認してください") == ["base_url", "LLMConfig"]
    assert _identifiers("Verify the address: {base_url_display}") == []
    assert _identifiers("Or set environment variable MYRM_TLS_STRICT=0") == ["MYRM_TLS_STRICT"]
    assert _identifiers("Enable debug logging") == ["debug"]
