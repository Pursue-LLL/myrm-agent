"""Turn setup steps: resume side effects, search gate, goal provider and runtime context of one agent turn."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from langgraph.types import Command
from myrm_agent_harness.agent.goals.protocols import GoalProvider

from app.services.agent.stream_session import orchestrator_turn_setup as setup

if TYPE_CHECKING:
    from app.ai_agents import GeneralAgentParams
    from app.services.agent.params import AgentRequest

CHAT_ID = "chat-setup"
CONVERTED = (
    SimpleNamespace(query="hello", enable_web_search=True, search_service_cfg=object()),
    "tier-1",
    "coding",
    "matched coding keywords",
    ["context warning"],
    [{"restored": True}],
)


def _request(**overrides: object) -> AgentRequest:
    fields: dict[str, object] = {
        "chat_id": CHAT_ID,
        "message_id": "msg-1",
        "action_mode": "agent",
        "agent_id": "default",
        "resume_value": None,
        "light_model_selection": None,
        "goal": None,
    }
    fields.update(overrides)
    return cast("AgentRequest", SimpleNamespace(**fields))


def _params(**overrides: object) -> GeneralAgentParams:
    fields: dict[str, object] = {"enable_web_search": True, "search_service_cfg": object()}
    fields.update(overrides)
    return cast("GeneralAgentParams", SimpleNamespace(**fields))


def _joined(**overrides: object) -> SimpleNamespace:
    fields = dict(preview=None, snapshot=None, brief_status={}, prewarm_hit=False, prewarm_ms=None, still_warming=False)
    return SimpleNamespace(**{**fields, **overrides})


@pytest.fixture
def converted_params(monkeypatch: pytest.MonkeyPatch) -> GeneralAgentParams:
    params = cast("GeneralAgentParams", SimpleNamespace(query="hello"))
    monkeypatch.setattr(
        setup,
        "convert_to_general_agent_params",
        AsyncMock(return_value=(params, *CONVERTED[1:])),
    )
    return params


class TestBuildTurnParams:
    @pytest.mark.asyncio
    async def test_fresh_turn_remembers_its_routing_and_seeds_no_context(
        self, monkeypatch: pytest.MonkeyPatch, converted_params: GeneralAgentParams
    ) -> None:
        remember = MagicMock()
        monkeypatch.setattr(setup, "remember_turn_routing", remember)
        request = _request()

        turn = await setup.build_turn_params(request, [], MagicMock())

        assert turn.params is converted_params
        assert (turn.routing_tier, turn.routing_specialty, turn.routing_reason) == CONVERTED[1:4]
        assert turn.context_warnings == CONVERTED[4]
        assert turn.archive_restore_results == CONVERTED[5]
        assert turn.extra_context is None
        remember.assert_called_once_with(request, tier="tier-1", specialty="coding", reason="matched coding keywords")

    @pytest.mark.asyncio
    async def test_resume_applies_takeover_decision_and_grant_then_marks_the_hitl_session_active(
        self, monkeypatch: pytest.MonkeyPatch, converted_params: GeneralAgentParams
    ) -> None:
        from app.services.agent import session_access_service
        from app.services.approvals.registry import ApprovalRegistry
        from app.services.chat.chat_service import ChatService

        resolve_takeover = AsyncMock()
        apply_grant = AsyncMock()
        remember = MagicMock()
        monkeypatch.setattr(ApprovalRegistry, "resolve_pending_browser_takeover_for_chat", resolve_takeover)
        monkeypatch.setattr(ChatService, "get_chat_metadata", AsyncMock(return_value=None))
        monkeypatch.setattr(session_access_service, "apply_directory_resume_grant", apply_grant)
        monkeypatch.setattr(setup, "remember_turn_routing", remember)
        resume_value = {"action": "completed", "message": ""}

        turn = await setup.build_turn_params(_request(resume_value=resume_value), [], MagicMock())

        resolve_takeover.assert_awaited_once_with(CHAT_ID, decision="approve")
        apply_grant.assert_awaited_once_with(CHAT_ID, resume_value, workspace_dir=None)
        assert turn.extra_context == {"hitl_session_active": True}
        assert isinstance(converted_params.query, Command)
        assert converted_params.query.resume == resume_value
        remember.assert_not_called()

    @pytest.mark.asyncio
    async def test_skipped_takeover_resumes_as_a_denial(
        self, monkeypatch: pytest.MonkeyPatch, converted_params: GeneralAgentParams
    ) -> None:
        from app.services.agent import session_access_service
        from app.services.approvals.registry import ApprovalRegistry
        from app.services.chat.chat_service import ChatService

        resolve_takeover = AsyncMock()
        monkeypatch.setattr(ApprovalRegistry, "resolve_pending_browser_takeover_for_chat", resolve_takeover)
        monkeypatch.setattr(ChatService, "get_chat_metadata", AsyncMock(return_value=None))
        monkeypatch.setattr(session_access_service, "apply_directory_resume_grant", AsyncMock())

        await setup.build_turn_params(_request(resume_value={"action": "skipped"}), [], MagicMock())

        resolve_takeover.assert_awaited_once_with(CHAT_ID, decision="deny")


class TestSearchServiceUnavailableDetail:
    @pytest.mark.parametrize(
        ("request_fields", "params_fields", "expected"),
        [
            ({"agent_id": "builtin-deep-search"}, {"enable_web_search": False}, "add a search service in Settings"),
            ({"action_mode": "fast"}, {"search_service_cfg": None}, "Fast search requires"),
        ],
    )
    def test_names_the_missing_search_service(
        self, request_fields: dict[str, object], params_fields: dict[str, object], expected: str
    ) -> None:
        detail = setup.search_service_unavailable_detail(_request(**request_fields), _params(**params_fields))

        assert detail is not None
        assert detail.startswith("Search service not configured.")
        assert expected in detail

    def test_reports_nothing_for_a_turn_that_does_not_need_search(self) -> None:
        assert setup.search_service_unavailable_detail(_request(), _params(enable_web_search=False)) is None

    def test_reports_nothing_when_the_search_service_is_configured(self) -> None:
        assert setup.search_service_unavailable_detail(_request(action_mode="fast"), _params()) is None


class TestPrepareGoalProvider:
    @pytest.mark.asyncio
    async def test_a_turn_without_a_chat_has_no_goal_provider(self) -> None:
        assert await setup.prepare_goal_provider(_request(chat_id=None), "hello") is None

    @pytest.mark.asyncio
    async def test_a_chat_without_a_goal_gets_its_registered_provider_untouched(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.services.agent.goals import goal_branch_stash
        from app.services.agent.goals.goal_registry import GoalRegistry

        provider = MagicMock()
        stash = AsyncMock()
        monkeypatch.setattr(goal_branch_stash, "check_and_handle_branch_stash", stash)
        monkeypatch.setattr(GoalRegistry, "get_or_create_provider", MagicMock(return_value=provider))

        result = await setup.prepare_goal_provider(_request(), "hello")

        assert result is provider
        stash.assert_awaited_once_with(CHAT_ID)
        provider.create_goal.assert_not_called()

    @pytest.mark.asyncio
    async def test_a_goal_request_creates_the_goal_from_the_message_when_none_is_active(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.services.agent.goals import goal_branch_stash
        from app.services.agent.goals.goal_registry import GoalRegistry

        provider = MagicMock()
        provider.get_active_goal = AsyncMock(return_value=None)
        provider.create_goal = AsyncMock()
        monkeypatch.setattr(goal_branch_stash, "check_and_handle_branch_stash", AsyncMock())
        monkeypatch.setattr(GoalRegistry, "get_or_create_provider", MagicMock(return_value=provider))

        await setup.prepare_goal_provider(_request(goal=_goal(checkpoint_mode="per_todo")), "  ship the release  ")

        kwargs = provider.create_goal.await_args.kwargs
        assert kwargs["session_id"] == CHAT_ID
        assert kwargs["objective"] == "ship the release"
        assert kwargs["ui_summary"] == "ship the release"
        assert kwargs["checkpoint_mode"] == "per_todo"
        assert kwargs["budget"].max_turns == 7

    @pytest.mark.asyncio
    async def test_a_goal_request_rebudgets_the_active_goal(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.services.agent.goals import goal_branch_stash
        from app.services.agent.goals.goal_registry import GoalRegistry

        provider = MagicMock()
        provider.get_active_goal = AsyncMock(return_value=SimpleNamespace(goal_id="goal-1"))
        provider.set_budget = AsyncMock()
        provider.create_goal = AsyncMock()
        monkeypatch.setattr(goal_branch_stash, "check_and_handle_branch_stash", AsyncMock())
        monkeypatch.setattr(GoalRegistry, "get_or_create_provider", MagicMock(return_value=provider))

        await setup.prepare_goal_provider(_request(goal=_goal()), "ship the release")

        provider.create_goal.assert_not_awaited()
        assert provider.set_budget.await_args.args[0] == "goal-1"

    @pytest.mark.asyncio
    async def test_an_unknown_checkpoint_mode_falls_back_to_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.services.agent.goals import goal_branch_stash
        from app.services.agent.goals.goal_registry import GoalRegistry

        provider = MagicMock()
        provider.get_active_goal = AsyncMock(return_value=None)
        provider.create_goal = AsyncMock()
        monkeypatch.setattr(goal_branch_stash, "check_and_handle_branch_stash", AsyncMock())
        monkeypatch.setattr(GoalRegistry, "get_or_create_provider", MagicMock(return_value=provider))

        await setup.prepare_goal_provider(_request(goal=_goal(checkpoint_mode="everything")), "")

        kwargs = provider.create_goal.await_args.kwargs
        assert kwargs["checkpoint_mode"] == "none"
        assert kwargs["objective"] == "User requested goal"


def _goal(**overrides: object) -> SimpleNamespace:
    fields: dict[str, object] = {
        "max_tokens": 1000,
        "max_usd": 1.0,
        "max_time_seconds": 600,
        "max_turns": 7,
        "convergence_window": 3,
        "loop_on_pause": False,
        "max_loop_restarts": 0,
        "acceptance_criteria": [],
        "ui_summary": None,
        "constraints": [],
        "protected_paths": [],
        "checkpoint_mode": "none",
    }
    fields.update(overrides)
    return SimpleNamespace(**fields)


class TestBuildTurnExtraContext:
    @pytest.fixture(autouse=True)
    def _runtime(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.core.channel_bridge import config_loader
        from app.services.agent import runtime_context

        async def runtime_context_of(*, execution_mode: object, base: dict[str, object] | None = None) -> dict[str, object]:
            return {**(base or {}), "execution_mode": execution_mode}

        monkeypatch.setattr(runtime_context, "build_agent_runtime_context", runtime_context_of)
        monkeypatch.setattr(runtime_context, "resolve_stream_execution_mode", lambda: "desktop")
        monkeypatch.setattr(
            config_loader,
            "load_user_configs",
            AsyncMock(return_value=SimpleNamespace(personal_settings_dict={"locale": "de", "suggestWorkflowMode": False})),
        )

    @pytest.mark.asyncio
    async def test_a_resume_keeps_its_seed_and_skips_the_prewarm_join(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.services.agent.execution_cache.prewarm import coordinator

        coordinator_factory = MagicMock()
        monkeypatch.setattr(coordinator, "get_turn_prewarm_coordinator", coordinator_factory)
        provider = MagicMock(spec=GoalProvider)

        context = await setup.build_turn_extra_context(
            _request(resume_value={"action": "completed"}),
            _params(),
            base={"hitl_session_active": True},
            goal_provider=provider,
        )

        assert context == {
            "hitl_session_active": True,
            "goal_provider": provider,
            "execution_mode": "desktop",
            "locale": "de",
            "suggest_workflow_mode": False,
        }
        coordinator_factory.assert_not_called()

    @pytest.mark.asyncio
    async def test_a_fresh_turn_joins_the_prewarm_and_hydrates_the_chat_deltas(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.services.agent.execution_cache.prewarm import coordinator
        from app.services.memory import ephemeral_delta_hydration

        join = AsyncMock(
            return_value=_joined(preview={"items": 1}, brief_status={"status": "ready"}, prewarm_hit=True, prewarm_ms=12)
        )
        hydrate = MagicMock()
        monkeypatch.setattr(coordinator, "get_turn_prewarm_coordinator", lambda: SimpleNamespace(join_for_turn=join))
        monkeypatch.setattr(ephemeral_delta_hydration, "ensure_chat_ephemeral_deltas_hydrated", hydrate)
        monkeypatch.setattr(setup, "resolve_turn_knowledge_pack", AsyncMock(return_value=None))
        params = _params()

        context = await setup.build_turn_extra_context(_request(), params, base=None, goal_provider=None)

        hydrate.assert_called_once_with(CHAT_ID)
        join.assert_awaited_once_with(params, action_mode="agent")
        assert context["goal_provider"] is None
        assert context["memory_brief_preview"] == {"items": 1}
        assert "memory_brief_snapshot" not in context
        assert context["memory_brief_status"] == {"status": "ready"}
        assert context["turn_prewarm_hit"] is True
        assert context["turn_prewarm_ms"] == 12
        assert context["turn_prewarm_still_warming"] is False
        assert "proactive_knowledge_pack" not in context

    @pytest.mark.asyncio
    async def test_the_pack_is_retrieved_beside_the_prewarm_join_and_handed_over_in_the_run_context(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.ai_agents.agent_middlewares import PROACTIVE_PACK_CONTEXT_KEY
        from app.services.agent.execution_cache.prewarm import coordinator
        from app.services.memory import ephemeral_delta_hydration

        scan_started = asyncio.Event()
        pack: dict[str, object] = {"snippets": [{"article_title": "Hotel Limits"}]}

        async def join(*_: object, **__: object) -> SimpleNamespace:
            # The join can only return once the scan has begun: awaiting them one after the other would hang here.
            await asyncio.wait_for(scan_started.wait(), timeout=1.0)
            return _joined()

        async def resolve(_: object) -> dict[str, object]:
            scan_started.set()
            return pack

        monkeypatch.setattr(coordinator, "get_turn_prewarm_coordinator", lambda: SimpleNamespace(join_for_turn=join))
        monkeypatch.setattr(ephemeral_delta_hydration, "ensure_chat_ephemeral_deltas_hydrated", MagicMock())
        monkeypatch.setattr(setup, "resolve_turn_knowledge_pack", resolve)

        context = await setup.build_turn_extra_context(_request(), _params(), base=None, goal_provider=None)

        assert context[PROACTIVE_PACK_CONTEXT_KEY] is pack

    @pytest.mark.asyncio
    async def test_a_locale_lookup_failure_leaves_the_context_without_it(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.core.channel_bridge import config_loader

        monkeypatch.setattr(config_loader, "load_user_configs", AsyncMock(side_effect=RuntimeError("config store down")))

        context = await setup.build_turn_extra_context(
            _request(resume_value={"action": "completed"}), _params(), base=None, goal_provider=None
        )

        assert "locale" not in context
        assert context["goal_provider"] is None
