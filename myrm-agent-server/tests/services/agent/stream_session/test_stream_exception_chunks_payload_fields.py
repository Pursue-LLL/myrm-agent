"""Payload fields of the structured error chunks: the message id the client correlates on, the recovery locale, the cooldown."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import cast
from unittest.mock import MagicMock, patch

import orjson
import pytest
from myrm_agent_harness.agent.config.exceptions import ConfigIncompleteError
from myrm_agent_harness.toolkits.llms.errors import MyrmLLMError
from myrm_agent_harness.toolkits.llms.errors.error_types import FailoverReason

from app.services.agent.gateway import AgentBusyError
from app.services.agent.stream_session import stream_exception_chunks
from app.services.agent.stream_session.stream_session_types import AgentStreamSession


def _make_session(message_id: str | None = "msg-1", locale: str | None = None) -> AgentStreamSession:
    session = cast(AgentStreamSession, MagicMock(spec=AgentStreamSession))
    session.params = MagicMock(message_id=message_id, locale=locale)
    session.request = MagicMock(chat_id=None, turn_capability_telemetry=None)
    session.collector = MagicMock()
    session.had_fatal_error = False
    session.turn_capability_terminal_recorded = False
    return session


async def _payload(exc: BaseException, session: AgentStreamSession) -> dict[str, object]:
    with patch("app.core.errors.llm_errors.generate_recovery_actions", return_value=[]):
        chunks = [chunk async for chunk in stream_exception_chunks.yield_stream_exception_chunks(session, exc)]
    assert len(chunks) == 1
    return cast(dict[str, object], orjson.loads(chunks[0][len("data: ") :]))


def _config_incomplete() -> BaseException:
    return ConfigIncompleteError(
        user_friendly_message={"en": "Model is not configured."},
        technical_details="missing model config",
        resolution_steps=["open settings"],
        error_code="model_not_configured",
    )


def _llm_error() -> BaseException:
    return MyrmLLMError(error_code=FailoverReason.MODEL_NOT_FOUND, default_msg="Model does not exist")


_STRUCTURED_ERRORS = [
    pytest.param(lambda: AgentBusyError("busy"), id="busy"),
    pytest.param(_config_incomplete, id="config-incomplete"),
    pytest.param(_llm_error, id="llm-error"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("make_exc", _STRUCTURED_ERRORS)
async def test_a_structured_error_keeps_the_message_id_of_the_turn(make_exc: Callable[[], BaseException]) -> None:
    payload = await _payload(make_exc(), _make_session(message_id="msg-7"))

    assert payload["messageId"] == "msg-7"


@pytest.mark.asyncio
@pytest.mark.parametrize("make_exc", _STRUCTURED_ERRORS)
@pytest.mark.parametrize("message_id", [None, ""])
async def test_a_structured_error_of_a_turn_without_message_id_gets_a_fresh_one(
    make_exc: Callable[[], BaseException], message_id: str | None
) -> None:
    payload = await _payload(make_exc(), _make_session(message_id=message_id))

    assert isinstance(payload["messageId"], str)
    uuid.UUID(payload["messageId"])


@pytest.mark.asyncio
@pytest.mark.parametrize(("locale", "expected_lang"), [("zh", "zh"), (None, "en"), ("", "en")])
async def test_recovery_actions_are_generated_in_the_session_language(locale: str | None, expected_lang: str) -> None:
    exc = _llm_error()
    with patch("app.core.errors.llm_errors.generate_recovery_actions", return_value=[]) as generate:
        chunks = [
            chunk async for chunk in stream_exception_chunks.yield_stream_exception_chunks(_make_session(locale=locale), exc)
        ]

    assert len(chunks) == 1
    generate.assert_called_once()
    assert generate.call_args.args[1] == expected_lang


@pytest.mark.asyncio
async def test_an_llm_error_whose_context_has_no_cooldown_carries_no_cooldown_field() -> None:
    exc = MyrmLLMError(
        error_code=FailoverReason.MODEL_NOT_FOUND,
        default_msg="Model does not exist",
        context={"provider": "acme"},
    )

    payload = await _payload(exc, _make_session())

    assert "cooldown_remaining_ms" not in payload
