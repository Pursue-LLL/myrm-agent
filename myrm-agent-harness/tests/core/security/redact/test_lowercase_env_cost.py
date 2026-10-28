"""The lower-case ``name_key=value`` detector does a bounded amount of work per start position.

A long run of ``[a-z0-9_]`` made of credential words and underscores (``key_key_key_…``) gave every start position a
match attempt that scanned to the end of the run, so the cost grew with the square of the length: 8 KB took seconds.
Names are bounded on both sides, so the same input now costs time proportional to its length.
"""

from __future__ import annotations

import time

import pytest

from myrm_agent_harness.core.security.redact import redact_sensitive_text

_BUDGET_SECONDS = 2.0


class TestLongRunsStayLinear:
    @pytest.mark.parametrize("unit", ["key_", "token_", "pass_", "pass_phrase_", "api_key_"])
    def test_underscore_run_of_credential_words(self, unit: str) -> None:
        text = unit * (8_000 // len(unit))
        start = time.process_time()
        assert redact_sensitive_text(text) == text
        assert time.process_time() - start < _BUDGET_SECONDS


class TestNamesStillMatch:
    @pytest.mark.parametrize(
        "text",
        [
            "openai_key=sk-live-1234567890abcdefghij",
            "db_pw=correct-horse-91-Zk3fQ9xL",
            "app.api.key=correct-horse-91-Zk3fQ9xL",
            f"openai_key_{'x' * 60}=correct-horse-91-Zk3fQ9xL",
        ],
    )  # fmt: skip
    def test_value_is_masked(self, text: str) -> None:
        out = redact_sensitive_text(text)
        assert "correct-horse-91-Zk3fQ9xL" not in out
        assert "1234567890abcdefghij" not in out
