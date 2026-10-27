"""A turn forced onto one external agent runs there or fails with guidance, never answered by another agent."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncGenerator
from types import SimpleNamespace

import pytest

from app.ai_agents.general_agent.stream_pipeline import execute_stream_pipeline

_ALLOWED = {
    "capabilities": [{"permission": "*", "pattern": "*"}],
    "permissions": {
        "spawn_subagent": "allow",
        "invoke_external_agent": "allow",
        "file_write": "ask",
        "shell_exec": "ask",
    },
    "yoloModeEnabled": False,
    "autoModeEnabled": False,
}
_ASK = {**_ALLOWED, "permissions": {**_ALLOWED["permissions"], "invoke_external_agent": "ask"}}
_DELEGATED = {"type": "tasks_steps", "data": "delegated"}


def _agent(
    *,
    backends: list[str] | None,
    locale: str | None = "en",
    security: dict[str, object] | None = None,
    channel: str | None = None,
    breaks_with: Exception | None = None,
) -> SimpleNamespace:
    """A ``GeneralAgent`` stand-in with only what the forced-delegate branch reads.

    ``backends`` is the pool the agent ends up with (None: no pool could be built); ``breaks_with`` makes the
    delegated turn raise after its first event. The stand-in has no ``jit_subagents`` or any other normal-path
    attribute, so a fall-through to the normal agent raises.
    """
    agent = SimpleNamespace(
        channel_name=channel,
        security_config_raw=_ALLOWED if security is None else security,
        locale=locale,
        _runtime_pool=None,
        delegated=[],
        queries=[],
        pool_requests=0,
    )

    async def ensure_pool() -> None:
        agent.pool_requests += 1
        agent._runtime_pool = SimpleNamespace(available_backends=backends) if backends is not None else None

    async def delegate(
        name: str, query: object, *, cancel_token: object = None, chat_id: str | None = None
    ) -> AsyncGenerator[dict[str, object]]:
        agent.delegated.append(name)
        agent.queries.append(query)
        yield _DELEGATED
        if breaks_with is not None:
            raise breaks_with

    agent._ensure_runtime_pool = ensure_pool
    agent._direct_delegate_stream = delegate
    return agent


async def _run(agent: SimpleNamespace, query: object = "hi") -> list[dict[str, object]]:
    return [event async for event in execute_stream_pipeline(agent, query, force_external_agent="echo-cli")]


async def test_an_available_agent_gets_the_turn() -> None:
    agent = _agent(backends=["echo-cli"])

    assert await _run(agent) == [_DELEGATED]
    assert agent.delegated == ["echo-cli"]


async def test_a_target_missing_from_the_pool_is_reported_and_not_answered_by_another_agent() -> None:
    agent = _agent(backends=["claude"])

    events = await _run(agent)

    assert [event["type"] for event in events] == ["error"]
    assert events[0]["diagnostic_result"]["error_type"] == "external_agent_unavailable"
    assert "echo-cli" in events[0]["data"]
    assert agent.delegated == []


async def test_a_target_without_any_pool_is_reported_the_same_way() -> None:
    agent = _agent(backends=None)

    events = await _run(agent)

    assert [event["diagnostic_result"]["error_type"] for event in events] == ["external_agent_unavailable"]
    assert agent.delegated == []


async def test_the_report_follows_the_session_language() -> None:
    events = await _run(_agent(backends=["claude"], locale="zh-CN"))

    assert events[0]["diagnostic_result"]["locale"] == "zh"
    assert events[0]["recovery_actions"][0]["url"] == "/settings/developer"


async def test_a_session_without_a_language_gets_english() -> None:
    events = await _run(_agent(backends=["claude"], locale=None))

    assert events[0]["diagnostic_result"]["locale"] == "en"


async def test_a_turn_the_security_policy_does_not_allow_is_sent_to_the_settings_and_never_reaches_the_agent() -> None:
    agent = _agent(backends=["echo-cli"], security=_ASK, locale="zh-CN")

    events = await _run(agent)

    assert [event["type"] for event in events] == ["error"]
    assert events[0]["diagnostic_result"]["error_type"] == "external_agent_denied"
    assert events[0]["diagnostic_result"]["locale"] == "zh"
    assert events[0]["recovery_actions"] == [{"id": "open_security_settings", "label": "打开设置", "url": "/settings/security"}]
    assert agent.delegated == [] and agent.pool_requests == 0  # not even a pool is built for a refused turn


async def test_the_refusal_shows_what_to_change_and_logs_the_policy_reason(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger="app.ai_agents.general_agent.forced_delegate"):
        events = await _run(_agent(backends=["echo-cli"], security=_ASK))

    shown = json.dumps(events)
    assert "invoke_external_agent" not in shown and "denied by" not in shown.lower()
    assert "blocked by security policy" in caplog.text and "invoke_external_agent" in caplog.text


async def test_a_delegation_that_breaks_midway_ends_with_guidance_and_not_with_the_exception(
    caplog: pytest.LogCaptureFixture,
) -> None:
    agent = _agent(backends=["echo-cli"], breaks_with=RuntimeError("socket 10.0.0.7 reset"))

    with caplog.at_level(logging.ERROR, logger="app.ai_agents.general_agent.forced_delegate"):
        events = await _run(agent)

    assert events[0] == _DELEGATED
    assert [event["type"] for event in events] == ["tasks_steps", "error"]
    assert events[1]["diagnostic_result"]["error_type"] == "external_agent_failed"
    assert "10.0.0.7" not in json.dumps(events)
    assert "10.0.0.7" in caplog.text  # the cause is in the log, with its traceback
    assert [record.exc_info is not None for record in caplog.records if record.levelno == logging.ERROR] == [True]


async def test_the_message_reaches_the_agent_as_the_user_wrote_it_without_a_routing_banner() -> None:
    agent = _agent(backends=["echo-cli"], channel="telegram")
    blocks = [{"type": "text", "text": "hi"}, {"type": "image_url", "image_url": {"url": "file:///tmp/a.png"}}]

    await _run(agent, "hi")
    await _run(agent, blocks)

    assert agent.queries == ["hi", blocks]


async def test_what_the_user_wrote_is_not_logged(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.DEBUG):
        await _run(_agent(backends=["echo-cli"]), "my private plan for the merger")

    assert "private plan" not in caplog.text
    routing = [record for record in caplog.records if "Direct routing" in record.getMessage()]
    assert [record.levelno for record in routing] == [logging.INFO]
