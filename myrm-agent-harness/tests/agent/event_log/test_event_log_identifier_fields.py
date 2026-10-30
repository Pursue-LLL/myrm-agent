"""An identifier an event carries is written as it is, so a reader can still join events by it.

A provider issues call ids as long mixed alphanumeric runs (``call_00_3nrnFlx48weKv0yTotV43729_vtx8763``), the shape the
entropy tier of the leak scan takes for a key. The tier is for free text; a field that holds an identifier is read by its
name, and the shapes the leak detector knows by their prefix (``sk-``, ``ghp_``) are still masked inside it.
"""

from __future__ import annotations

import pytest

from myrm_agent_harness.agent.event_log._sanitize import sanitize_event_data

_PROVIDER_IDS = {
    "deepseek": "call_00_3nrnFlx48weKv0yTotV43729_vtx8763",
    "openai": "call_Xk3mQ9rT7vB2nL5pW8sY1dFh",
    "anthropic": "toolu_01A09q90qw90lq917835lq9Zk",
    "uuid": "3f2b8c1e-9d4a-4e7b-8a61-5c0d2f9e7b34",
}
_HIGH_ENTROPY_TEXT = "Zq8Xv2Lm9Tp4Rk7Ws1Yb5Nc3Hd6Jf0Ga"
_GITHUB_TOKEN = "ghp_" + "aB3dE5fG7hI9jK1lM3nO5pQ7rS9tU1vW3xY5"


@pytest.mark.parametrize("call_id", _PROVIDER_IDS.values(), ids=_PROVIDER_IDS.keys())
@pytest.mark.parametrize("key", ["tool_call_id", "id", "message_id", "toolCallId", "request-id", "TOOL_CALL_ID"])
def test_an_identifier_field_is_written_as_it_is(key: str, call_id: str) -> None:
    payload: dict[str, object] = {key: call_id}

    assert sanitize_event_data(payload) == payload


def test_the_identifiers_in_a_list_and_at_depth_are_written_as_they_are() -> None:
    call_id = _PROVIDER_IDS["deepseek"]
    payload: dict[str, object] = {"tool_call_ids": [call_id], "args": {"parent": {"tool_call_id": call_id}}}

    assert sanitize_event_data(payload) == payload


def test_a_token_shape_inside_an_identifier_field_is_still_masked() -> None:
    written = str(sanitize_event_data({"tool_call_id": _GITHUB_TOKEN}))

    assert _GITHUB_TOKEN not in written


def test_the_entropy_tier_still_reads_every_field_that_is_not_an_identifier() -> None:
    written = str(sanitize_event_data({"note": f"see {_HIGH_ENTROPY_TEXT}", "valid": _HIGH_ENTROPY_TEXT}))

    assert _HIGH_ENTROPY_TEXT not in written


@pytest.mark.parametrize("key", ["valid", "android", "paid", "idle_time", "identity"])
def test_a_name_that_only_ends_in_the_letters_id_is_not_an_identifier_field(key: str) -> None:
    written = str(sanitize_event_data({key: _HIGH_ENTROPY_TEXT}))

    assert _HIGH_ENTROPY_TEXT not in written
