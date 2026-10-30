"""A credential that is a number (``"password": 834921``) is masked by the name of its field at every exit.

A number has no shape for a scan, so the field name decides, like it does for a string. Every exit of the redaction
domain applies the same rule: the trace API, the event log write, the approval display, the walker the exports share
and the text rule for JSON in a string. A counter that only looks like a credential (``max_tokens``) stays a number.
"""

from __future__ import annotations

import json
from collections.abc import Callable

import pytest

from myrm_agent_harness.agent.event_log._sanitize import sanitize_event_data
from myrm_agent_harness.core.security.redact import redact_field_text, redact_for_display, redact_nested
from myrm_agent_harness.core.security.redact.engine import redact_sensitive_text
from myrm_agent_harness.infra.tracing.sanitizer import TraceSpanSanitizer

_NUMBER = 834921
_FLOAT = 4829175.3068

type Exit = Callable[[dict[str, object]], str]

_EXITS: dict[str, Exit] = {
    "trace_api": lambda payload: str(TraceSpanSanitizer().sanitize_payload(payload)),
    "event_log_write": lambda payload: str(sanitize_event_data(payload)),
    "approval_display": lambda payload: str(redact_for_display(payload)),
    "shared_walker": lambda payload: str(redact_nested(payload, redact_field_text)),
    "json_text": lambda payload: redact_sensitive_text(json.dumps(payload)),
}
_STRUCTURED_EXITS = {name: run for name, run in _EXITS.items() if name != "json_text"}

_CREDENTIAL_KEYS = ["password", "db_password", "token", "api_key", "client_secret", "passcode", "api_secret"]
_COUNTER_KEYS = ["max_tokens", "token_count", "input_tokens", "total_tokens", "cache_key_count", "password_length"]


@pytest.mark.parametrize("exit_name", _EXITS)
@pytest.mark.parametrize("key", _CREDENTIAL_KEYS)
def test_a_number_under_a_credential_name_is_masked_at_every_exit(exit_name: str, key: str) -> None:
    written = _EXITS[exit_name]({"args": {key: _NUMBER}})

    assert str(_NUMBER) not in written


@pytest.mark.parametrize("exit_name", _STRUCTURED_EXITS)
def test_a_decimal_number_and_a_list_of_numbers_under_a_credential_name_are_masked(exit_name: str) -> None:
    written = _STRUCTURED_EXITS[exit_name]({"password": _FLOAT, "steps": [{"passcode": [11223344, 55667788]}]})

    for value in ("4829175", "11223344", "55667788"):
        assert value not in written


@pytest.mark.parametrize("exit_name", _EXITS)
@pytest.mark.parametrize("key", _COUNTER_KEYS)
def test_a_counter_that_only_looks_like_a_credential_stays_a_number(exit_name: str, key: str) -> None:
    written = _EXITS[exit_name]({"usage": {key: 4096}})

    assert "4096" in written


@pytest.mark.parametrize("exit_name", ["event_log_write", "approval_display", "shared_walker"])
def test_a_flag_and_a_null_under_a_credential_name_are_left_as_they_are(exit_name: str) -> None:
    payload: dict[str, object] = {"token": None, "password": False, "api_key": True}

    assert _STRUCTURED_EXITS[exit_name](payload) == str(payload)


def test_the_walker_returns_a_number_under_an_ordinary_name_as_the_same_object() -> None:
    payload: dict[str, object] = {"count": _NUMBER, "ratio": _FLOAT}

    assert redact_nested(payload, redact_field_text) == payload
