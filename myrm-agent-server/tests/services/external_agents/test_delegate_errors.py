"""Direct delegation failures: what the user is told to do about them."""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator

import pytest
from myrm_agent_harness.api import AgentEventType
from myrm_agent_harness.toolkits.acp.types import (
    AcpError,
    AcpErrorCode,
    RuntimeConfig,
    RuntimeEvent,
    RuntimeEventType,
    create_event,
)

from app.schemas.streaming import SSEEnvelope
from app.services.external_agents.delegate_errors import agent_unavailable_event, delegate_error_event
from app.services.external_agents.direct_delegate_stream import SseEvent, stream_direct_delegate

_SETTINGS_URL = "/settings/developer"

# (error code, auth mode of the agent, expected error_type)
_GUIDED = [
    (AcpErrorCode.AUTH_FAILED, "subscription", "external_agent_auth_subscription"),
    (AcpErrorCode.AUTH_FAILED, "api_key", "external_agent_auth_api_key"),
    (AcpErrorCode.BACKEND_NOT_FOUND, "subscription", "external_agent_not_installed"),
    (AcpErrorCode.TIMEOUT, "subscription", "external_agent_timeout"),
]
_GUIDED_CODES = {code for code, _, _ in _GUIDED}
_UNGUIDED = [code for code in AcpErrorCode if code not in _GUIDED_CODES]


def _failure(code: AcpErrorCode, auth_mode: str = "subscription", locale: str = "en") -> SseEvent:
    error = AcpError(code=code, message="raw cli text")
    event = delegate_error_event("claude", error, auth_mode=auth_mode, locale=locale)
    assert event is not None
    return event


def _diagnostic(event: SseEvent) -> dict[str, object]:
    diagnostic = event["diagnostic_result"]
    assert isinstance(diagnostic, dict)
    return diagnostic


@pytest.mark.parametrize(("code", "auth_mode", "error_type"), _GUIDED)
@pytest.mark.parametrize("locale", ["en", "zh", "zh-CN", "ja", "de-DE", ""])
def test_guidance_follows_the_frontend_error_contract(code: AcpErrorCode, auth_mode: str, error_type: str, locale: str) -> None:
    event = _failure(code, auth_mode, locale)
    diagnostic = _diagnostic(event)

    assert event["type"] == AgentEventType.ERROR.value
    assert event["data"] == diagnostic["user_message"]
    assert diagnostic["error_type"] == error_type
    assert diagnostic["locale"] in {"en", "zh"}
    assert "claude" in str(diagnostic["user_message"])
    steps = diagnostic["resolution_steps"]
    assert isinstance(steps, list) and steps and all(isinstance(step, str) for step in steps)
    for text in [str(diagnostic["user_message"]), *steps]:
        assert "{" not in text and "}" not in text  # no unfilled placeholder


@pytest.mark.parametrize(
    ("locale", "language"),
    [
        ("zh", "zh"),
        ("zh-CN", "zh"),
        ("ZH_cn", "zh"),
        ("en", "en"),
        ("en-US", "en"),
        ("ja", "en"),
        ("ko", "en"),
        ("de", "en"),
        ("", "en"),
    ],
)
def test_guidance_follows_the_session_language(locale: str, language: str) -> None:
    diagnostic = _diagnostic(_failure(AcpErrorCode.AUTH_FAILED, locale=locale))

    assert diagnostic["locale"] == language
    assert str(diagnostic["user_message"]).startswith("claude 尚未登录") == (language == "zh")


@pytest.mark.parametrize(("code", "auth_mode", "error_type"), _GUIDED)
def test_guidance_says_what_to_do_and_not_what_broke(code: AcpErrorCode, auth_mode: str, error_type: str) -> None:
    for locale in ("en", "zh"):
        assert "raw cli text" not in json.dumps(_failure(code, auth_mode, locale), ensure_ascii=False)


@pytest.mark.parametrize(("code", "auth_mode", "error_type"), _GUIDED)
def test_a_fix_in_the_settings_comes_with_a_button_to_the_settings_page(
    code: AcpErrorCode, auth_mode: str, error_type: str
) -> None:
    event = _failure(code, auth_mode)

    if code is AcpErrorCode.TIMEOUT:
        assert "recovery_actions" not in event
        return
    actions = event["recovery_actions"]
    assert isinstance(actions, list) and len(actions) == 1
    assert actions[0]["url"] == _SETTINGS_URL
    assert actions[0]["label"]
    assert ("install" in actions[0]["id"]) == (code is AcpErrorCode.BACKEND_NOT_FOUND)


@pytest.mark.parametrize("code", _UNGUIDED, ids=lambda code: code.value)
def test_other_failures_keep_the_words_of_the_cli(code: AcpErrorCode) -> None:
    error = AcpError(code=code, message="raw cli text")

    assert delegate_error_event("claude", error, auth_mode="subscription", locale="en") is None


def test_an_unavailable_agent_is_an_error_with_a_way_to_the_settings() -> None:
    event = agent_unavailable_event("codex", "zh-CN")
    diagnostic = _diagnostic(event)

    assert diagnostic["error_type"] == "external_agent_unavailable"
    assert diagnostic["locale"] == "zh"
    assert "codex" in str(diagnostic["user_message"])
    assert event["recovery_actions"] == [{"id": "open_external_agents", "label": "打开设置", "url": _SETTINGS_URL}]


def test_the_guidance_reaches_the_frontend_through_the_sse_envelope() -> None:
    event = _failure(AcpErrorCode.BACKEND_NOT_FOUND)

    chunk = SSEEnvelope.from_any(event).to_sse_chunk()
    payload = json.loads(chunk.removeprefix("data: "))

    assert payload["diagnostic_result"] == event["diagnostic_result"]
    assert payload["recovery_actions"] == event["recovery_actions"]


class _FailingPool:
    """A ``DelegationPool`` whose only turn fails with ``error``."""

    available_backends = ["claude"]

    def __init__(self, error: AcpError, auth_mode: str = "subscription") -> None:
        self._error = error
        self._config = RuntimeConfig(backend_type="cli", auth_mode="api_key" if auth_mode == "api_key" else "subscription")

    def get_config(self, name: str) -> RuntimeConfig:
        return self._config

    async def run_turn(
        self, name: str, prompt: str, session_id: str, *, mode: str = "persistent", mcp_servers: object = None
    ) -> AsyncGenerator[RuntimeEvent]:
        yield create_event(RuntimeEventType.ERROR, session_id, error=self._error)

    async def cancel(self, name: str, session_id: str) -> None:
        return None


async def _errors(pool: _FailingPool, locale: str = "en") -> tuple[list[SseEvent], list[SseEvent]]:
    events = [event async for event in stream_direct_delegate(pool, "claude", "do it", session_id="claude-chat-1", locale=locale)]
    return events, [event for event in events if event["type"] == AgentEventType.ERROR.value]


async def test_a_signed_out_agent_ends_the_turn_with_guidance_in_the_session_language() -> None:
    pool = _FailingPool(AcpError(code=AcpErrorCode.AUTH_FAILED, message="Not logged in"))

    events, errors = await _errors(pool, locale="zh")

    assert errors == [_failure(AcpErrorCode.AUTH_FAILED, locale="zh")]
    assert events[-2]["status"] == "error"
    assert events[-1]["type"] == AgentEventType.MESSAGE_END.value


async def test_a_rejected_api_key_is_told_apart_from_a_signed_out_login() -> None:
    pool = _FailingPool(AcpError(code=AcpErrorCode.AUTH_FAILED, message="401"), auth_mode="api_key")

    _, errors = await _errors(pool)

    assert [_diagnostic(error)["error_type"] for error in errors] == ["external_agent_auth_api_key"]


async def test_a_failure_the_user_cannot_fix_still_shows_the_cli_text() -> None:
    pool = _FailingPool(AcpError(code=AcpErrorCode.PROCESS_CRASHED, message="claude exited with code 1"))

    _, errors = await _errors(pool)

    assert errors == [{"type": AgentEventType.ERROR.value, "data": "claude exited with code 1"}]
