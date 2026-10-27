"""A goal turn the server starts for itself takes the session and carries a cancel token before its agent is built.

Checked against the real gateway and cancellation registry; only the agent stream is a stand-in. The chat Stop
button, a pause and the emergency stop reach a turn through that session claim and that token, so a turn without
them cannot be stopped from outside.
"""

import asyncio
import uuid
from collections.abc import AsyncGenerator, AsyncIterator, Callable, Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.agent.goals.types import Goal, GoalBudget, GoalStatus
from myrm_agent_harness.utils.runtime.cancellation import CancellationRegistry, CancellationToken, CancelReason

from app.services.agent.gateway import AgentDrainingError, get_agent_gateway
from app.services.agent.goals import goal_controls, goal_stream_trigger

_WAIT_SECONDS = 2.0


@pytest.fixture
def chat_id() -> Iterator[str]:
    chat = f"goal-turn-{uuid.uuid4().hex[:8]}"
    yield chat
    # The gateway is one per process: a failing test must not leave its session busy for the next one.
    get_agent_gateway().release_session(chat)


def _goal(chat: str) -> Goal:
    return Goal(
        goal_id="g-runtime",
        session_id=chat,
        objective="Long run",
        status=GoalStatus.ACTIVE,
        budget=GoalBudget(max_turns=5),
    )


@dataclass
class _Agent:
    """Stands in for ``ai_agent_service_stream``: notes what the trigger handed it, then takes the session like the real one."""

    chat: str
    claims_session: bool = True
    raises: BaseException | None = None
    gate: asyncio.Event = field(default_factory=asyncio.Event)
    entered: asyncio.Event = field(default_factory=asyncio.Event)
    running: asyncio.Event = field(default_factory=asyncio.Event)
    calls: int = 0
    cancel_token: CancellationToken | None = None
    session_was_active: bool = False
    turn_id: str | None = None

    async def __call__(self, _params: object, **kwargs: object) -> AsyncIterator[dict[str, object]]:
        gateway = get_agent_gateway()
        self.calls += 1
        token = kwargs.get("cancel_token")
        self.cancel_token = token if isinstance(token, CancellationToken) else None
        self.session_was_active = gateway.is_session_active(self.chat)
        self.turn_id = gateway.get_active_message_id(self.chat)
        self.entered.set()
        if self.raises is not None:
            raise self.raises
        if not self.claims_session:
            return
        async for event in gateway.execute_stream(self._events(), agent_type="general", session_id=self.chat):
            yield event

    async def _events(self) -> AsyncGenerator[dict[str, object], None]:
        self.running.set()
        await self.gate.wait()
        yield {"type": "tick"}


@contextmanager
def _trigger_environment(stream: Callable[..., AsyncIterator[object]]) -> Iterator[AsyncMock]:
    """Everything ``trigger_goal_stream`` loads before it starts the headless stream, with ``stream`` as the agent.

    Yields the failure handler the stream's errors go to.
    """
    with ExitStack() as stack:
        stack.enter_context(patch("app.services.agent.streaming.ai_agent_service_stream", stream))
        handler = stack.enter_context(
            patch(
                "app.services.agent.goals.goal_stream_trigger.handle_unattended_goal_stream_failure",
                new_callable=AsyncMock,
            )
        )
        stack.enter_context(patch("app.ai_agents.GeneralAgentParams", side_effect=lambda **kwargs: MagicMock(**kwargs)))
        stack.enter_context(
            patch(
                "app.core.channel_bridge.config_loader.load_user_configs",
                new_callable=AsyncMock,
                return_value=MagicMock(
                    providers_dict={},
                    retrieval_dict={},
                    security_config_dict={"yolo_mode_enabled": True},
                    search_cfg=None,
                    search_is_user_configured=False,
                ),
            )
        )
        stack.enter_context(
            patch(
                "app.core.channel_bridge.model_resolver.resolve_model_config",
                return_value=MagicMock(supports_vision=False, model="fake/test"),
            )
        )
        stack.enter_context(
            patch(
                "app.core.channel_bridge.model_resolver.enrich_model_capabilities",
                side_effect=lambda cfg, *_args, **_kwargs: cfg,
            )
        )
        stack.enter_context(
            patch("app.core.channel_bridge.model_resolver.enrich_model_context_window", side_effect=lambda cfg, _: cfg)
        )
        stack.enter_context(
            patch("app.core.channel_bridge.config_parsers.extract_fallback_model_configs", return_value=(None, None))
        )
        stack.enter_context(patch("app.core.channel_bridge.config_parsers.extract_retrieval_models", return_value=(None, None)))
        stack.enter_context(
            patch(
                "app.core.channel_bridge.config_parsers.verify_search_service_available",
                new_callable=AsyncMock,
                return_value=False,
            )
        )
        stack.enter_context(
            patch(
                "app.core.skills.gates.disabled_skill_roots.collect_disabled_skill_roots",
                new_callable=AsyncMock,
                return_value=[],
            )
        )
        yield handler


async def _start(chat: str, provider: AsyncMock | None = None) -> None:
    await goal_stream_trigger.trigger_goal_stream(
        chat, _goal(chat), provider=provider or AsyncMock(), on_failure="needs_human_review", context="runtime test"
    )


async def _settle() -> None:
    """Wait for every goal stream the trigger started to end; call it once the stand-in agent is no longer held."""
    pending = tuple(goal_stream_trigger._running_goal_tasks)
    if pending:
        await asyncio.wait_for(asyncio.gather(*pending), timeout=_WAIT_SECONDS)


def _released(chat: str, turn_id: str | None) -> bool:
    """Whether the turn gave back its session and its cancel token."""
    return not get_agent_gateway().is_session_active(chat) and (turn_id is None or not CancellationRegistry.cancel(turn_id))


@pytest.mark.asyncio
async def test_the_turn_holds_the_session_and_a_cancel_token_before_its_agent_is_built(chat_id: str) -> None:
    agent = _Agent(chat_id, claims_session=False)

    with _trigger_environment(agent):
        await _start(chat_id)
        await asyncio.wait_for(agent.entered.wait(), timeout=_WAIT_SECONDS)
        await _settle()

    assert agent.session_was_active
    assert agent.turn_id is not None
    assert agent.cancel_token is not None
    assert agent.cancel_token.request_id == agent.turn_id


@pytest.mark.asyncio
async def test_a_pause_stops_the_turn_the_server_started_through_its_cancel_token(chat_id: str) -> None:
    agent = _Agent(chat_id)

    with _trigger_environment(agent):
        await _start(chat_id)
        await asyncio.wait_for(agent.running.wait(), timeout=_WAIT_SECONDS)
        assert get_agent_gateway().get_active_message_id(chat_id) == agent.turn_id
        assert agent.cancel_token is not None
        assert not agent.cancel_token.is_cancelled

        assert goal_controls.stop_goal_turn(chat_id, _goal(chat_id))

        assert agent.cancel_token.is_cancelled
        assert goal_controls.is_turn_stopping(chat_id)
        agent.gate.set()
        await _settle()

    assert not goal_controls.is_turn_stopping(chat_id)
    assert _released(chat_id, agent.turn_id)


@pytest.mark.asyncio
async def test_an_emergency_stop_cancels_the_turn_the_server_started(chat_id: str) -> None:
    agent = _Agent(chat_id)

    with _trigger_environment(agent):
        await _start(chat_id)
        await asyncio.wait_for(agent.running.wait(), timeout=_WAIT_SECONDS)
        assert agent.cancel_token is not None

        assert CancellationRegistry.cancel_all(CancelReason.ESTOP) >= 1

        assert agent.cancel_token.is_cancelled
        agent.gate.set()
        await _settle()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("agent_kwargs", "failure_reported"),
    [
        pytest.param({}, False, id="ran_to_the_end"),
        pytest.param({"claims_session": False}, False, id="ended_without_taking_the_session"),
        pytest.param({"raises": RuntimeError("mid stream")}, True, id="failed_before_taking_the_session"),
    ],
)
async def test_the_turn_gives_back_its_session_and_cancel_token_however_it_ends(
    chat_id: str, agent_kwargs: dict[str, object], failure_reported: bool
) -> None:
    agent = _Agent(chat_id, **agent_kwargs)  # type: ignore[arg-type]
    provider = AsyncMock()

    with _trigger_environment(agent) as handler:
        await _start(chat_id, provider)
        await asyncio.wait_for(agent.entered.wait(), timeout=_WAIT_SECONDS)
        agent.gate.set()
        await _settle()

    assert agent.turn_id is not None
    assert _released(chat_id, agent.turn_id)
    assert handler.await_count == int(failure_reported)
    if failure_reported:
        handler.assert_awaited_once_with(chat_id, "g-runtime", provider, on_failure="needs_human_review", context="runtime test")


@pytest.mark.asyncio
async def test_a_session_taken_by_a_message_is_left_to_it_and_nothing_is_built(chat_id: str) -> None:
    """A message that took the session first carries the goal on: the start is neither a failure nor a theft of its claim."""
    gateway = get_agent_gateway()
    gateway.reserve_session(chat_id, active_message_id="user-message")
    agent = _Agent(chat_id)
    provider = AsyncMock()

    with _trigger_environment(agent) as handler:
        await _start(chat_id, provider)
        await _settle()

    assert agent.calls == 0
    handler.assert_not_awaited()
    provider.update_status.assert_not_called()
    assert gateway.get_active_message_id(chat_id) == "user-message"
    assert gateway.is_session_active(chat_id)


@pytest.mark.asyncio
async def test_a_second_start_leaves_the_first_turn_running_and_builds_nothing(chat_id: str) -> None:
    first = _Agent(chat_id)
    second = _Agent(chat_id)

    with _trigger_environment(first) as handler:
        await _start(chat_id)
        await asyncio.wait_for(first.running.wait(), timeout=_WAIT_SECONDS)

        with patch("app.services.agent.streaming.ai_agent_service_stream", second):
            await _start(chat_id)
            await asyncio.sleep(0.05)

        assert second.calls == 0
        assert get_agent_gateway().get_active_message_id(chat_id) == first.turn_id
        assert first.cancel_token is not None
        assert not first.cancel_token.is_cancelled
        first.gate.set()
        await _settle()

    handler.assert_not_awaited()
    assert _released(chat_id, first.turn_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("drain_starts", ["before_the_session_is_taken", "while_the_agent_is_built"])
async def test_a_start_that_meets_a_draining_app_is_not_a_goal_failure(chat_id: str, drain_starts: str) -> None:
    gateway = get_agent_gateway()
    agent = _Agent(
        chat_id, raises=AgentDrainingError("Gateway is draining") if drain_starts == "while_the_agent_is_built" else None
    )
    provider = AsyncMock()

    with (
        _trigger_environment(agent) as handler,
        patch.object(gateway, "_draining", drain_starts == "before_the_session_is_taken"),
    ):
        await _start(chat_id, provider)
        await _settle()

    handler.assert_not_awaited()
    provider.update_status.assert_not_called()
    assert agent.calls == int(drain_starts == "while_the_agent_is_built")
    assert _released(chat_id, agent.turn_id)
