"""Architecture test: server tests must not commit complete provider-shaped credentials.

GitHub push protection rejects any pushed text that contains a whole provider-shaped token, fake
or not. Fixtures assemble such values through ``tests/support/fake_secrets.py`` instead.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.support.fake_secrets import slack_bot_token, stripe_live_key

_TESTS_ROOT = Path(__file__).resolve().parent.parent
_SCANNED_SUFFIXES = frozenset({".py", ".json", ".jsonl", ".md", ".txt", ".yml", ".yaml", ".toml", ".ts", ".tsx", ".js"})

# Shapes push protection blocks today. Add a pattern (and a matching helper) when a new provider is rejected.
_PROVIDER_TOKEN_PATTERNS: dict[str, re.Pattern[str]] = {
    "Stripe secret/restricted key": re.compile(r"\b(?:sk|rk)_(?:live|test)_[0-9A-Za-z]{20,}"),
    "Slack bot/user token": re.compile(r"\bxox[abposr]-\d{9,}-\d{9,}(?:-\d{9,})?-[A-Za-z0-9]{16,}"),
}


def _scanned_files() -> list[Path]:
    return [
        path
        for path in _TESTS_ROOT.rglob("*")
        if path.is_file() and path.suffix in _SCANNED_SUFFIXES and "__pycache__" not in path.parts
    ]


@pytest.mark.architecture
def test_patterns_detect_helper_output() -> None:
    """The guard must keep matching what the fixture helpers build, otherwise the scan passes vacuously."""
    assert _PROVIDER_TOKEN_PATTERNS["Stripe secret/restricted key"].search(stripe_live_key("123456789012345678901234"))
    assert _PROVIDER_TOKEN_PATTERNS["Slack bot/user token"].search(
        slack_bot_token("123456789012-1234567890123-abcdefghijklmnopqrstuvwx")
    )


@pytest.mark.architecture
def test_no_complete_provider_tokens_in_tests() -> None:
    violations: list[str] = []
    for path in _scanned_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        for line_no, line in enumerate(text.splitlines(), start=1):
            for label, pattern in _PROVIDER_TOKEN_PATTERNS.items():
                if pattern.search(line):
                    violations.append(f"{path.relative_to(_TESTS_ROOT.parent)}:{line_no}: {label}")
    assert not violations, (
        "Complete provider-shaped tokens are blocked by GitHub push protection. "
        "Build them with tests/support/fake_secrets.py:\n" + "\n".join(violations)
    )
