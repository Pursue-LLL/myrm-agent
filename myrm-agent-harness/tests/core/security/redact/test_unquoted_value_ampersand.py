"""A ``&`` inside an unquoted value belongs to the secret unless it starts the next form parameter.

``.env`` files, YAML configs and compose files hold passwords such as ``PASSWORD=ab&cd``; a value that stopped at the
``&`` left ``&cd`` readable. A ``&`` ends the value only when a ``key=`` pair (``token=abc&page=1``) or ``amp;`` (the
HTML-escaped separator) follows, so form bodies and query strings keep their other parameters.
"""

from __future__ import annotations

import time

import pytest

from myrm_agent_harness.core.security.redact import redact_sensitive_text

_TAIL = "Def456!Ghi789#JklMno"
_VALUE = f"Abc123&{_TAIL}"

# shape -> (text, the name that must stay visible)
_SHAPES: dict[str, tuple[str, str]] = {
    "env-export": (f"export API_TOKEN={_VALUE}", "API_TOKEN"),
    "env-inline": (f"CLIENT_SECRET={_VALUE} run.sh", "CLIENT_SECRET"),
    "env-lower": (f"db_token={_VALUE}", "db_token"),
    "env-password": (f"export DB_PASSWORD={_VALUE}", "DB_PASSWORD"),
    "compose-list": (f"    - POSTGRES_PASSWORD={_VALUE}", "POSTGRES_PASSWORD"),
    "yaml": (f"api_key: {_VALUE}", "api_key"),
    "yaml-nested": (f"services:\n  db:\n    password: {_VALUE}\n", "password"),
}


class TestAmpersandInsideValueIsMasked:
    @pytest.mark.parametrize("shape", _SHAPES)
    def test_tail_after_the_ampersand_is_masked(self, shape: str) -> None:
        text, name = _SHAPES[shape]
        out = redact_sensitive_text(text)
        assert "Def456" not in out
        assert _TAIL not in out
        assert name in out

    def test_value_after_an_ampersand_is_masked_with_the_rest(self) -> None:
        assert redact_sensitive_text("POSTGRES_PASSWORD=ab&cd") == "POSTGRES_PASSWORD=***"

    def test_text_after_the_value_stays(self) -> None:
        assert redact_sensitive_text(f"CLIENT_SECRET={_VALUE} run.sh").endswith(" run.sh")


class TestSeparatorsStillEndTheValue:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("token=abcdef&page=1&limit=5", "token=***&page=1&limit=5"),
            ('curl -d "token=abcdef&page=1&limit=5" https://x', 'curl -d "token=***&page=1&limit=5" https://x'),
            ("see https://x/y?id=1&token=abcdef&limit=50 now", "see https://x/y?id=1&token=***&limit=50 now"),
            ("x?id=1&amp;token=abcdef&amp;limit=50", "x?id=1&amp;token=***&amp;limit=50"),
            ("x_token=abcd&a=1&b=2 and password=hunter2&z=9", "x_token=***&a=1&b=2 and password=***&z=9"),
            ("run API_KEY=abcdef&&echo done", "run API_KEY=***&&echo done"),
            ("A_TOKEN=abc& next", "A_TOKEN=***& next"),
            ("password: &anchor", "password: &anchor"),
        ],
    )  # fmt: skip
    def test_ampersand_before_a_pair_a_second_ampersand_or_a_space_is_not_part_of_the_value(
        self, text: str, expected: str
    ) -> None:
        assert redact_sensitive_text(text) == expected


class TestAmpersandRunsStayLinear:
    @pytest.mark.parametrize("unit", ["&a", "&abc", "&a=", "a&b"])
    def test_long_run_after_an_assignment(self, unit: str) -> None:
        for prefix in ("API_TOKEN=", "db_token=", "api_key: "):
            text = prefix + unit * (16_000 // len(unit))
            start = time.process_time()
            redact_sensitive_text(text)
            assert time.process_time() - start < 2.0
