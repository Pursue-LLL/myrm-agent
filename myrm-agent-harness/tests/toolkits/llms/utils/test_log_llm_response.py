"""log_llm_response only displays a response: the dict the caller turns into a message must come out untouched."""

from __future__ import annotations

import copy
import logging

import pytest

from myrm_agent_harness.toolkits.llms.utils.logger import log_llm_response


def _answer() -> dict[str, object]:
    return {
        "model": "claude-test",
        "choices": [
            {
                "finish_reason": "tool_calls",
                "message": {
                    "role": "assistant",
                    "content": "checking",
                    "provider_specific_fields": {"thought_signature": "sig-field"},
                    "thinking_blocks": [{"type": "thinking", "thinking": '{"plan": 1}', "signature": "sig-block"}],
                    "tool_calls": [
                        {
                            "id": "toolu_01ABC",
                            "type": "function",
                            "provider_specific_fields": {"thought_signature": "sig-call"},
                            "function": {"name": "get_weather", "arguments": '{"city": "Tokyo"}'},
                        },
                        {
                            "id": "toolu_01DEF",
                            "type": "function",
                            "function": {"name": "get_weather", "arguments": '{"city": "Paris"}'},
                        },
                    ],
                },
            }
        ],
        "usage": {
            "prompt_tokens": 100,
            "completion_tokens": 20,
            "total_tokens": 120,
            "prompt_tokens_details": {"cached_tokens": 40},
            "completion_tokens_details": {"reasoning_tokens": 5},
        },
    }


def test_the_response_comes_out_exactly_as_it_went_in() -> None:
    response = _answer()
    before = copy.deepcopy(response)

    log_llm_response(response)

    assert response == before, "ids, argument strings and signatures are what the message is built from"


def test_the_log_still_shows_decoded_arguments_without_the_noisy_fields(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="myrm_agent_harness.toolkits.llms.utils.logger"):
        log_llm_response(_answer())

    text = caplog.text
    assert '"city": "Tokyo"' in text, "arguments are shown decoded, as JSON"
    assert "toolu_01ABC" not in text and "sig-block" not in text and "sig-call" not in text
    assert "Cached Tokens: 40" in text and "Reasoning Tokens: 5" in text


def test_a_response_without_choices_is_logged_without_error(caplog: pytest.LogCaptureFixture) -> None:
    response: dict[str, object] = {"model": "m", "choices": [], "usage": {}}

    with caplog.at_level(logging.INFO, logger="myrm_agent_harness.toolkits.llms.utils.logger"):
        log_llm_response(response)

    assert "N/A (empty choices)" in caplog.text
