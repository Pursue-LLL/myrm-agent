"""Context guard data models and token-pressure estimation.

[INPUT]
- dataclasses::dataclass, field (POS: Python 数据类标准库)
- collections::Counter (POS: Python 字符计数标准库)
- unicodedata::unicodedata (POS: Python Unicode 东亚宽度标准库)

[OUTPUT]
- TRANSIENT_SPILLOVER_DIR / KEPT_SPILLOVER_DIR: workspace-relative directories of the two spill lifetimes
- ContextGuardConfig: thresholds controlling when a payload is spilled
- SpilloverPayload / SpilloverResult: spilled-file metadata and evaluation outcome
- estimate_token_pressure: token estimate that weighs each character by its kind (wide, capital, digit, symbol, ...)

[POS]
Value-object and measurement layer of the context guard subsystem. Keeps the token
estimate next to the config it feeds, since a naive chars/4 heuristic would under-count
CJK text by three to four times and dense ASCII (hex, base64, logs, minified JSON) by up
to 2.7 times, and let oversized payloads slip past the guard. The estimate is a pure
function of the text on purpose: ``utils.text_utils.get_token_count`` loads its BPE data
on first use and falls back to a coarser estimate when that fails, so the same text could
be parked by one entry point and kept by another. The directory names live here because
the spill writer, the sweeper and the file read tool's path scope must agree on them. No
filesystem access.
"""

from __future__ import annotations

import unicodedata
from collections import Counter
from dataclasses import dataclass, field

# A spill nothing refers to after the turn: the sweeper removes it after the TTL.
TRANSIENT_SPILLOVER_DIR = ".myrm/spillover"
# A spill a stored conversation points at: no sweeper is configured for it, its owner removes it.
KEPT_SPILLOVER_DIR = ".myrm/pastes"


@dataclass(slots=True)
class ContextGuardConfig:
    """Configuration for message size limits, the token-pressure limit, and spillover paths."""

    max_message_chars: int = 16_000
    # Equivalent token threshold (e.g. 8,000 tokens)
    max_token_pressure: int = 8_000
    # Characters of the start and of the end of a spilled text that stay in the prompt.
    preview_chars: int = 300
    spillover_dir_name: str = TRANSIENT_SPILLOVER_DIR
    spillover_ttl_seconds: int = 86_400  # 24 hours


# What one character adds to the estimate, in hundredths of a token. Whole numbers keep the sum exact, so a
# language that mirrors this estimate (the composer in the web UI) rounds it the same way.
_PLAIN_WEIGHT = 25  # a lowercase letter or white space: prose is cheap
_SYMBOL_WEIGHT = 40  # any other ASCII character: punctuation, operators, control codes
_DIGIT_WEIGHT = 75
_UPPER_WEIGHT = 100  # capitals are rare in prose and frequent in ids, hashes and base64
_ALPHABET_WEIGHT = 50  # a non-ASCII narrow character: Cyrillic, Arabic, Indic, Thai, accented Latin
# East Asian wide and fullwidth characters (CJK, kana, hangul, emoji). Above the 0.8-0.95 o200k_base measures for
# Chinese and Japanese on purpose: other tokenizers split them finer, and a text parked early costs one file read.
_WIDE_WEIGHT = 180


def _centi_weight(char: str) -> int:
    if char < "\x80":
        if "a" <= char <= "z" or char in " \t\n\r":
            return _PLAIN_WEIGHT
        if "A" <= char <= "Z":
            return _UPPER_WEIGHT
        if "0" <= char <= "9":
            return _DIGIT_WEIGHT
        return _SYMBOL_WEIGHT
    if unicodedata.east_asian_width(char) in ("W", "F") or "\u4e00" <= char <= "\u9fff":
        return _WIDE_WEIGHT
    return _ALPHABET_WEIGHT


def estimate_token_pressure(text: str) -> int:
    """Estimate how many tokens a text costs, from the kind of each character.

    A proxy, not a tokenizer: English prose costs about 0.2 token per character, while hex, base64, logs, URLs
    and minified JSON cost 0.4-0.7 (digits, capitals and symbols break into short pieces), Thai and Indic text
    about 0.35-0.5, and CJK about 0.8-1.0. Weighing every non-CJK character the same would let a dense text of
    twice the tokens pass a limit set for prose. The weights are fitted to tiktoken ``o200k_base``: against the
    recorded samples in ``tests/agent/context_guard/test_token_pressure.py`` the estimate stays within 0.4x-1.3x
    of the real count. Other tokenizers split non-Latin text into more tokens than ``o200k_base`` does.
    """
    return sum(_centi_weight(char) * count for char, count in Counter(text).items()) // 100


@dataclass(slots=True)
class SpilloverPayload:
    """Metadata describing a spilled file payload."""

    spill_id: str
    file_path: str
    relative_path: str
    char_count: int
    line_count: int
    estimated_tokens: int
    sha256_digest: str
    summary_preview: str
    original_role: str = "user"
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class SpilloverResult:
    """Result of context guard evaluation on an incoming message."""

    spilled: bool
    sanitized_content: str
    payload: SpilloverPayload | None = None
    original_char_count: int = 0
    estimated_tokens: int = 0
