"""The composer's long-paste notice and the server's parking must trigger on the same text.

The frontend tells a person that a paste will be kept in a file before it is sent; it can only be right
while its limits and character weights equal the ones the context guard applies to the text of a person.
"""

from __future__ import annotations

import re
from pathlib import Path

from myrm_agent_harness.agent.context_guard import estimate_token_pressure

from app.services.chat.context_bomb_guard import USER_TEXT_LIMITS

_SPILLOVER_TS = Path(__file__).resolve().parents[3] / "myrm-agent-frontend" / "src" / "lib" / "utils" / "spillover.ts"


def _ts_number(name: str) -> float:
    source = _SPILLOVER_TS.read_text(encoding="utf-8")
    match = re.search(rf"\b{name}\s*=\s*([0-9_.]+)\s*;", source)
    assert match is not None, f"{name} is not defined in {_SPILLOVER_TS.name}"
    return float(match.group(1).replace("_", ""))


def test_frontend_limits_equal_the_limits_of_the_text_of_a_person() -> None:
    assert _ts_number("SPILLOVER_MIN_CHARS") == USER_TEXT_LIMITS.max_message_chars
    assert _ts_number("SPILLOVER_MAX_TOKEN_PRESSURE") == USER_TEXT_LIMITS.max_token_pressure
    assert _ts_number("SPILLOVER_PREVIEW_CHARS") == USER_TEXT_LIMITS.preview_chars


def test_frontend_character_weights_equal_the_engine_estimate() -> None:
    wide, narrow = _ts_number("WIDE_CHARACTER_WEIGHT"), _ts_number("NARROW_CHARACTER_WEIGHT")

    assert estimate_token_pressure("字" * 1_000) == int(1_000 * wide)
    assert estimate_token_pressure("a" * 1_000) == int(1_000 * narrow)
