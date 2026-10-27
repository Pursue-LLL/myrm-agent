"""Direct delegation failures: what the user is told to do about them."""

from __future__ import annotations

import json
import logging
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
from app.services.external_agents.delegation.errors import (
    agent_unavailable_event,
    delegate_denied_event,
    delegate_error_event,
    delegate_failed_event,
)
from app.services.external_agents.delegation.stream import SseEvent, stream_direct_delegate

_SETTINGS_URL = "/settings/developer"
_SECURITY_URL = "/settings/security"

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


def _api_key_steps(locale: str, api_key_env: tuple[str, ...]) -> list[str]:
    error = AcpError(code=AcpErrorCode.AUTH_FAILED, message="raw cli text")
    event = delegate_error_event("claude", error, auth_mode="api_key", locale=locale, api_key_env=api_key_env)
    assert event is not None
    steps = _diagnostic(event)["resolution_steps"]
    assert isinstance(steps, list)
    return steps


@pytest.mark.parametrize(("locale", "where"), [("en", "Environment variables"), ("zh", "环境变量")])
def test_a_rejected_api_key_names_the_variables_the_agent_reads_it_from(locale: str, where: str) -> None:
    steps = _api_key_steps(locale, ("GEMINI_API_KEY", "GOOGLE_API_KEY"))

    assert "GEMINI_API_KEY / GOOGLE_API_KEY" in steps[0]
    assert where in steps[0]
    assert all("{" not in step and "}" not in step for step in steps)


def test_a_rejected_api_key_without_known_variables_keeps_the_general_steps() -> None:
    assert _api_key_steps("en", ()) == _diagnostic(_failure(AcpErrorCode.AUTH_FAILED, "api_key"))["resolution_steps"]
    assert _api_key_steps("en", ())[0] == "Check the API key under Settings → Developer → External Agents."


@pytest.mark.parametrize("code", [AcpErrorCode.AUTH_FAILED, AcpErrorCode.BACKEND_NOT_FOUND, AcpErrorCode.TIMEOUT])
def test_variable_names_belong_only_to_the_api_key_guidance(code: AcpErrorCode) -> None:
    error = AcpError(code=code, message="raw cli text")

    named = delegate_error_event("claude", error, auth_mode="subscription", locale="en", api_key_env=("ANTHROPIC_API_KEY",))

    assert named == _failure(code, "subscription")


@pytest.mark.parametrize("code", _UNGUIDED, ids=lambda code: code.value)
def test_other_failures_keep_the_words_of_the_cli(code: AcpErrorCode) -> None:
    error = AcpError(code=code, message="raw cli text")

    assert delegate_error_event("claude", error, auth_mode="subscription", locale="en") is None


# Failures the pipeline raises before any CLI turn exists: (event builder, expected error_type)
_STANDALONE = [
    (agent_unavailable_event, "external_agent_unavailable"),
    (delegate_denied_event, "external_agent_denied"),
    (delegate_failed_event, "external_agent_failed"),
]


@pytest.mark.parametrize(("build", "error_type"), _STANDALONE)
@pytest.mark.parametrize("locale", ["en", "zh", "zh-CN", "ja", ""])
def test_a_failure_before_any_turn_follows_the_frontend_error_contract(build, error_type: str, locale: str) -> None:
    event = build("codex", locale)
    diagnostic = _diagnostic(event)

    assert event["type"] == AgentEventType.ERROR.value
    assert event["data"] == diagnostic["user_message"]
    assert diagnostic["error_type"] == error_type
    assert diagnostic["locale"] in {"en", "zh"}
    steps = diagnostic["resolution_steps"]
    assert isinstance(steps, list) and steps and all(isinstance(step, str) for step in steps)
    for text in [str(diagnostic["user_message"]), *steps]:
        assert "{" not in text and "}" not in text  # no unfilled placeholder
    assert "codex" in str(diagnostic["user_message"])


def test_an_unavailable_agent_is_an_error_with_a_way_to_the_settings() -> None:
    event = agent_unavailable_event("codex", "zh-CN")
    diagnostic = _diagnostic(event)

    assert diagnostic["error_type"] == "external_agent_unavailable"
    assert diagnostic["locale"] == "zh"
    assert "codex" in str(diagnostic["user_message"])
    assert event["recovery_actions"] == [{"id": "open_external_agents", "label": "打开设置", "url": _SETTINGS_URL}]


def test_a_denied_delegation_sends_the_user_to_the_security_policy_in_their_language() -> None:
    english = delegate_denied_event("codex", "en")
    chinese = delegate_denied_event("codex", "zh")

    assert english["recovery_actions"] == [{"id": "open_security_settings", "label": "Open Settings", "url": _SECURITY_URL}]
    assert chinese["recovery_actions"] == [{"id": "open_security_settings", "label": "打开设置", "url": _SECURITY_URL}]
    assert "Security Policy" in " ".join(_diagnostic(english)["resolution_steps"])
    assert "安全策略" in " ".join(_diagnostic(chinese)["resolution_steps"])
    # The user reads what to change, never the policy engine's wording of the refusal.
    visible = " ".join([str(english["data"]), *_diagnostic(english)["resolution_steps"]]).lower()
    assert "denied" not in visible and "blocked" not in visible and "reason" not in visible


def test_a_broken_delegation_asks_for_a_retry_and_points_to_the_settings() -> None:
    event = delegate_failed_event("claude", "en")

    assert _diagnostic(event)["resolution_steps"][0] == "Send your message again."
    assert event["recovery_actions"] == [{"id": "open_external_agents", "label": "Open Settings", "url": _SETTINGS_URL}]


def test_the_guidance_reaches_the_frontend_through_the_sse_envelope() -> None:
    event = _failure(AcpErrorCode.BACKEND_NOT_FOUND)

    chunk = SSEEnvelope.from_any(event).to_sse_chunk()
    payload = json.loads(chunk.removeprefix("data: "))

    assert payload["diagnostic_result"] == event["diagnostic_result"]
    assert payload["recovery_actions"] == event["recovery_actions"]


class _FailingPool:
    """A ``DelegationPool`` whose only turn fails with ``error``."""

    available_backends = ["claude"]

    def __init__(self, error: AcpError, auth_mode: str = "subscription", command: str | None = None) -> None:
        self._error = error
        self._config = RuntimeConfig(
            backend_type="cli", command=command, auth_mode="api_key" if auth_mode == "api_key" else "subscription"
        )

    def get_config(self, name: str) -> RuntimeConfig:
        return self._config

    async def run_turn(
        self,
        name: str,
        prompt: str,
        session_id: str,
        *,
        mode: str = "persistent",
        mcp_servers: object = None,
        images: list[str] | None = None,
    ) -> AsyncGenerator[RuntimeEvent]:
        yield create_event(RuntimeEventType.ERROR, session_id, error=self._error)

    async def cancel(self, name: str, session_id: str) -> None:
        return None


async def _errors(pool: _FailingPool, locale: str = "en", agent: str = "claude") -> tuple[list[SseEvent], list[SseEvent]]:
    events = [event async for event in stream_direct_delegate(pool, agent, "do it", session_id=f"{agent}-chat-1", locale=locale)]
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


@pytest.mark.parametrize(
    ("agent", "command", "variable"),
    [
        ("claude", None, "ANTHROPIC_API_KEY"),
        ("reviewer", "/usr/local/bin/codex", "OPENAI_API_KEY"),
    ],
    ids=["by-agent-name", "by-command"],
)
async def test_a_rejected_api_key_names_the_variable_of_the_agent_that_ran(
    agent: str, command: str | None, variable: str
) -> None:
    pool = _FailingPool(AcpError(code=AcpErrorCode.AUTH_FAILED, message="401"), auth_mode="api_key", command=command)

    _, errors = await _errors(pool, agent=agent)

    (steps,) = [_diagnostic(error)["resolution_steps"] for error in errors]
    assert variable in steps[0]


async def test_a_rejected_api_key_of_an_unknown_agent_gets_the_general_steps() -> None:
    pool = _FailingPool(AcpError(code=AcpErrorCode.AUTH_FAILED, message="401"), auth_mode="api_key", command="/opt/my-agent")

    _, errors = await _errors(pool, agent="my-agent")

    assert [_diagnostic(error)["resolution_steps"] for error in errors] == [_api_key_steps("en", ())]


async def test_a_failure_the_user_cannot_fix_still_shows_the_cli_text() -> None:
    pool = _FailingPool(AcpError(code=AcpErrorCode.PROCESS_CRASHED, message="claude exited with code 1"))

    _, errors = await _errors(pool)

    assert errors == [{"type": AgentEventType.ERROR.value, "data": "claude exited with code 1"}]


_STREAM_LOGGER = "app.services.external_agents.delegation.stream"


def _failure_logs(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [record for record in caplog.records if record.getMessage().startswith("external_agent_failure")]


async def test_the_cli_words_behind_the_guidance_are_logged_without_credentials(caplog: pytest.LogCaptureFixture) -> None:
    key = "sk-ant-api03-" + "a1B2c3D4e5F6g7H8i9J0" * 2
    pool = _FailingPool(AcpError(code=AcpErrorCode.AUTH_FAILED, message=f"Invalid API key {key} for claude"))

    with caplog.at_level(logging.WARNING, logger=_STREAM_LOGGER):
        events, _ = await _errors(pool)

    (record,) = _failure_logs(caplog)
    assert record.levelno == logging.WARNING
    assert "agent=claude" in record.getMessage() and "code=auth_failed" in record.getMessage()
    assert "Invalid API key" in record.getMessage()
    assert key not in caplog.text
    assert key not in json.dumps(events)  # the user is shown steps, never the CLI's words


async def test_the_logged_cli_words_are_cut_to_their_start(caplog: pytest.LogCaptureFixture) -> None:
    pool = _FailingPool(AcpError(code=AcpErrorCode.TIMEOUT, message="slow " * 2000))

    with caplog.at_level(logging.WARNING, logger=_STREAM_LOGGER):
        await _errors(pool)

    (record,) = _failure_logs(caplog)
    assert len(record.getMessage()) < 700


async def test_a_failure_shown_with_the_cli_words_is_not_logged_a_second_time(caplog: pytest.LogCaptureFixture) -> None:
    pool = _FailingPool(AcpError(code=AcpErrorCode.PROCESS_CRASHED, message="claude exited with code 1"))

    with caplog.at_level(logging.WARNING, logger=_STREAM_LOGGER):
        await _errors(pool)

    assert _failure_logs(caplog) == []
