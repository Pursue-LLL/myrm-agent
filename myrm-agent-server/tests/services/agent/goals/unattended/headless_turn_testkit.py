"""Real-gateway scaffolding for the goal turns the server starts for itself.

Everything runs for real (gateway, cancellation registry, goal registry, storage) except the agent stream, which ``Agent``
stands in for, and what ``trigger_goal_stream`` loads before it starts that stream, which ``trigger_environment`` replaces.
"""

import asyncio
from collections.abc import AsyncGenerator, AsyncIterator, Callable, Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
from unittest.mock import AsyncMock, MagicMock, patch

from myrm_agent_harness.agent.goals.protocols import GoalProvider
from myrm_agent_harness.agent.goals.types import Goal, GoalBudget, GoalStatus
from myrm_agent_harness.utils.runtime.cancellation import CancellationRegistry, CancellationToken

from app.services.agent.gateway import get_agent_gateway
from app.services.agent.goals.goal_registry import GoalRegistry
from app.services.agent.goals.unattended import trigger

WAIT_SECONDS = 2.0


def goal_for(chat: str) -> Goal:
    """A goal that exists only in memory: nothing is stored for the chat."""
    return Goal(
        goal_id="g-runtime",
        session_id=chat,
        objective="Long run",
        status=GoalStatus.ACTIVE,
        budget=GoalBudget(max_turns=5),
    )


@dataclass
class Agent:
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
    registered_provider: GoalProvider | None = None
    context_provider: object = None

    async def __call__(self, _params: object, **kwargs: object) -> AsyncIterator[dict[str, object]]:
        gateway = get_agent_gateway()
        self.calls += 1
        token = kwargs.get("cancel_token")
        self.cancel_token = token if isinstance(token, CancellationToken) else None
        self.session_was_active = gateway.is_session_active(self.chat)
        self.turn_id = gateway.get_active_message_id(self.chat)
        # What the agent about to be built sees: the registry its goal tools are mounted from, and the stream context
        # its goal callbacks are wired from.
        self.registered_provider = GoalRegistry.get_provider(self.chat)
        extra_context = kwargs.get("extra_context")
        self.context_provider = extra_context.get("goal_provider") if isinstance(extra_context, dict) else None
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
def trigger_environment(stream: Callable[..., AsyncIterator[object]]) -> Iterator[AsyncMock]:
    """Everything ``trigger_goal_stream`` loads before it starts the headless stream, with ``stream`` as the agent.

    Yields the failure handler the stream's errors go to.
    """
    with ExitStack() as stack:
        stack.enter_context(patch("app.services.agent.streaming.ai_agent_service_stream", stream))
        handler = stack.enter_context(
            patch(
                "app.services.agent.goals.unattended.trigger.handle_unattended_goal_stream_failure",
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


async def start(chat: str, goal: Goal | None = None) -> None:
    """Start the goal's headless turn the way a goal callback does."""
    await trigger.trigger_goal_stream(chat, goal or goal_for(chat), context="runtime test")


async def settle() -> None:
    """Wait for every goal stream the trigger started to end; call it once the stand-in agent is no longer held."""
    pending = tuple(trigger._running_goal_tasks)
    if pending:
        await asyncio.wait_for(asyncio.gather(*pending), timeout=WAIT_SECONDS)


def released(chat: str, turn_id: str | None) -> bool:
    """Whether the turn gave back its session and its cancel token."""
    return not get_agent_gateway().is_session_active(chat) and (turn_id is None or not CancellationRegistry.cancel(turn_id))
