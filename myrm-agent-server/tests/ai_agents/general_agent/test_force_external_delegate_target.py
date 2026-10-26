"""Direct delegation to an external agent that is not available is an error, never an answer from another agent."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from types import SimpleNamespace

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
_DELEGATED = {"type": "tasks_steps", "data": "delegated"}


def _agent(*, backends: list[str] | None, locale: str | None = "en") -> SimpleNamespace:
    """A ``GeneralAgent`` stand-in with only what the forced-delegate branch reads.

    ``backends`` is the pool the agent ends up with (None: no pool could be built). The stand-in has no
    ``jit_subagents`` or any other normal-path attribute, so a fall-through to the normal agent raises.
    """
    agent = SimpleNamespace(
        channel_name=None,
        security_config_raw=_ALLOWED,
        locale=locale,
        _runtime_pool=None,
        delegated=[],
    )

    async def ensure_pool() -> None:
        agent._runtime_pool = SimpleNamespace(available_backends=backends) if backends is not None else None

    async def delegate(
        name: str, query: object, *, cancel_token: object = None, chat_id: str | None = None
    ) -> AsyncGenerator[dict[str, object]]:
        agent.delegated.append(name)
        yield _DELEGATED

    agent._ensure_runtime_pool = ensure_pool
    agent._direct_delegate_stream = delegate
    return agent


async def _run(agent: SimpleNamespace) -> list[dict[str, object]]:
    return [event async for event in execute_stream_pipeline(agent, "hi", force_external_agent="echo-cli")]


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
