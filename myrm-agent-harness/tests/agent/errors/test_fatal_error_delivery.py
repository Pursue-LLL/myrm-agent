"""A fatal LLM failure reaches the host as exactly one ``error`` event, never as an exception.

Hosts (web finalize, IM channels, cron, kanban) consume ``SkillAgent.run`` as an event stream. The
diagnosis, recovery actions and provider boundary live on that event; a host that waits for an
escaping ``MyrmLLMError`` instead never sees one. The whole chain runs for real here (agent loop,
stream executor, failover classifier, diagnostic engine); only the LLM is a stub that fails the way
a provider answers: xAI for an account without credits, Anthropic for an overloaded service.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path

import pytest
import pytest_asyncio
from langchain_core.callbacks import AsyncCallbackManagerForLLMRun, CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessageChunk, BaseMessage
from langchain_core.outputs import ChatGenerationChunk, ChatResult

from myrm_agent_harness.agent.skill_agent import SkillAgent, wait_all_background_tasks
from myrm_agent_harness.agent.streaming.recovery.stream_recovery_window import ProviderWindowRecoveryMixin
from myrm_agent_harness.backends.skills.local import LocalSkillBackend

_XAI_NO_CREDITS_BODY = {
    "code": "The caller does not have permission to execute the specified operation",
    "error": "Your team has either used all available credits or reached its monthly spending limit.",
}


_ANTHROPIC_OVERLOADED_BODY = {"type": "error", "error": {"type": "overloaded_error", "message": "Overloaded"}}


class _XaiEntitlementError(Exception):
    status_code = 403

    def __init__(self) -> None:
        self.body = _XAI_NO_CREDITS_BODY
        super().__init__(f"Error code: 403 - {self.body}")


class _AnthropicOverloadedError(Exception):
    status_code = 503

    def __init__(self) -> None:
        self.body = _ANTHROPIC_OVERLOADED_BODY
        super().__init__(f"Error code: 503 - {self.body}")


class _FailingLLM(BaseChatModel):
    """An LLM whose every call raises the error ``_failure`` builds."""

    model_name: str = "stub"

    @property
    def _llm_type(self) -> str:
        return "failing"

    def _failure(self) -> Exception:
        raise NotImplementedError

    def bind_tools(self, tools: object, **kwargs: object) -> _FailingLLM:
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: object,
    ) -> ChatResult:
        raise self._failure()

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: object,
    ) -> ChatResult:
        raise self._failure()

    async def _astream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: object,
    ) -> AsyncIterator[ChatGenerationChunk]:
        raise self._failure()
        yield ChatGenerationChunk(message=AIMessageChunk(content=""))


class _EntitlementFailingLLM(_FailingLLM):
    model_name: str = "grok-4"

    def _failure(self) -> Exception:
        return _XaiEntitlementError()


class _OverloadedLLM(_FailingLLM):
    model_name: str = "claude-sonnet"

    def _failure(self) -> Exception:
        return _AnthropicOverloadedError()


@dataclass(frozen=True)
class _Delivery:
    events: list[dict[str, object]]
    escaped: Exception | None

    @property
    def error_events(self) -> list[dict[str, object]]:
        return [event for event in self.events if event.get("type") == "error"]


async def _run_until_it_fails(llm: BaseChatModel, root: Path) -> _Delivery:
    (root / "skills").mkdir()
    agent = SkillAgent(llm=llm, skill_backend=LocalSkillBackend(root / "skills"))
    context: dict[str, object] = {
        "workspaces_storage_root": str(root / "ws"),
        "session_id": "fatal-delivery",
        "chat_id": "fatal-delivery",
    }
    events: list[dict[str, object]] = []
    escaped: Exception | None = None
    try:
        async for event in agent.run("hello", context=context):
            events.append(event)
    except Exception as exc:
        escaped = exc
    await wait_all_background_tasks()
    return _Delivery(events=events, escaped=escaped)


@pytest_asyncio.fixture(scope="module")
async def delivery(tmp_path_factory: pytest.TempPathFactory) -> _Delivery:
    return await _run_until_it_fails(_EntitlementFailingLLM(), tmp_path_factory.mktemp("fatal_delivery"))


@pytest_asyncio.fixture(scope="module")
async def overloaded_delivery(tmp_path_factory: pytest.TempPathFactory) -> _Delivery:
    async def no_wait(self: ProviderWindowRecoveryMixin, seconds: float) -> bool:
        return True

    # An overloaded provider is retried with a growing wait before the failure turns fatal; the wait is all this skips.
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(ProviderWindowRecoveryMixin, "_sleep_unless_cancelled", no_wait)
        return await _run_until_it_fails(_OverloadedLLM(), tmp_path_factory.mktemp("fatal_delivery_overloaded"))


async def test_no_exception_escapes_the_run(delivery: _Delivery) -> None:
    assert delivery.escaped is None


async def test_exactly_one_error_event_carries_the_diagnosis(delivery: _Delivery) -> None:
    (error_event,) = delivery.error_events

    assert error_event["error_kind"] == "billing"
    assert error_event["failover_reason"] == "billing"
    diagnostic = error_event["diagnostic_result"]
    assert isinstance(diagnostic, dict)
    assert diagnostic["error_type"] == "billing"
    assert diagnostic["user_message"] == "Your API account balance is insufficient"
    assert diagnostic["resolution_steps"]


async def test_error_event_offers_the_account_recovery_action(delivery: _Delivery) -> None:
    (error_event,) = delivery.error_events
    actions = error_event["recovery_actions"]

    assert isinstance(actions, list)
    assert "top_up" in [action["id"] for action in actions]


async def test_an_overloaded_provider_reads_as_overload_not_as_the_raw_exception(
    overloaded_delivery: _Delivery,
) -> None:
    assert overloaded_delivery.escaped is None
    (error_event,) = overloaded_delivery.error_events

    assert error_event["error_kind"] == "overloaded"
    diagnostic = error_event["diagnostic_result"]
    assert isinstance(diagnostic, dict)
    assert diagnostic["error_type"] == "overloaded"
    assert diagnostic["user_message"] == "The AI service is temporarily overloaded"
    assert "503" not in str(diagnostic["user_message"])
    assert diagnostic["resolution_steps"]
