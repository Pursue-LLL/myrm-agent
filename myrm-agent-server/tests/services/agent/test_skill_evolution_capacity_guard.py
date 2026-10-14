"""Skill evolution capacity guard: count-only check and one user notice per full library."""

import asyncio
from collections.abc import Iterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.agent.skills.evolution import (
    BudgetStatus,
    EvolutionType,
    SkillBudgetConfig,
    SkillBudgetGovernor,
)

from app.services.agent.evolution import engine
from app.services.agent.evolution.engine import (
    check_skill_budget_before_evolution,
    trigger_skill_evolution,
)

_STORE_GETTER = "app.core.skills.store.evolution_store.get_evolution_skill_store"
_RUN_TASK = "app.services.agent.evolution.engine._run_evolution_task"
_PUBLISH_NOTICE = "app.services.agent.evolution.engine.publish_skill_capacity_reached_event"
_LIFECYCLE = "app.core.skills.curator.service.describe_skill_lifecycle"
_CAP = 10
_LIVE = (False, False)  # (archived, pinned) of an installed, unarchived skill
_ARCHIVED = (True, False)


@pytest.fixture(autouse=True)
def _isolated_engine_state() -> Iterator[None]:
    engine._LIBRARY_FULL_NOTIFIED.clear()
    engine._RUNNING_EVOLUTION_TASKS.clear()
    yield
    engine._LIBRARY_FULL_NOTIFIED.clear()
    engine._RUNNING_EVOLUTION_TASKS.clear()


@pytest.fixture(autouse=True)
def _every_skill_is_live() -> Iterator[None]:
    with patch(_LIFECYCLE, return_value=_LIVE):
        yield


@pytest.fixture
def governor() -> SkillBudgetGovernor:
    return SkillBudgetGovernor(SkillBudgetConfig(max_skill_count=_CAP))


@pytest.fixture
def model_cfg() -> MagicMock:
    return MagicMock()


def _store_with(count: int) -> MagicMock:
    store = MagicMock()
    store.count_active_skills.return_value = count
    records = [MagicMock() for _ in range(count)]
    for index, record in enumerate(records):
        record.name = f"skill-{index}"
    store.get_active_skills.return_value = records
    return store


def _lifecycle_of(states: dict[str, tuple[bool, bool] | None]):
    """Lifecycle probe answering per skill name; unlisted skills are installed and unarchived."""
    return lambda name: states.get(name, _LIVE)


def _trigger(chat_id: str, model_cfg: MagicMock, governor: SkillBudgetGovernor, agent_id: str | None = None) -> None:
    trigger_skill_evolution(
        chat_id=chat_id,
        model_cfg=model_cfg,
        tool_steps_count=5,
        agent_id=agent_id,
        governor=governor,
    )


def test_budget_check_counts_skills_without_loading_their_bodies(governor: SkillBudgetGovernor) -> None:
    store = _store_with(2)

    with patch(_STORE_GETTER, return_value=store):
        result = check_skill_budget_before_evolution(
            agent_id="agent-1",
            evolution_type=EvolutionType.CAPTURED,
            governor=governor,
        )

    store.count_active_skills.assert_called_once_with(agent_id="agent-1")
    store.get_active_skills.assert_not_called()
    assert result.allowed is True
    assert result.status == BudgetStatus.NORMAL
    assert (result.current_count, result.max_count) == (2, _CAP)


def test_budget_check_blocks_new_skills_when_the_library_is_full(governor: SkillBudgetGovernor) -> None:
    with patch(_STORE_GETTER, return_value=_store_with(_CAP)):
        result = check_skill_budget_before_evolution(
            agent_id="agent-1",
            evolution_type=EvolutionType.CAPTURED,
            governor=governor,
        )

    assert result.allowed is False
    assert result.status == BudgetStatus.FULL


def test_budget_check_fails_open_when_the_store_is_unavailable(governor: SkillBudgetGovernor) -> None:
    with patch(_STORE_GETTER, side_effect=RuntimeError("skills.db unavailable")):
        result = check_skill_budget_before_evolution(agent_id="agent-1", governor=governor)

    assert result.allowed is True
    assert result.status == BudgetStatus.NORMAL


def test_deleted_skills_stop_counting_once_the_library_looks_full(governor: SkillBudgetGovernor) -> None:
    store = _store_with(_CAP)
    deleted = {f"skill-{index}": None for index in range(3)}

    with patch(_STORE_GETTER, return_value=store), patch(_LIFECYCLE, side_effect=_lifecycle_of(deleted)):
        result = check_skill_budget_before_evolution(agent_id="agent-1", governor=governor)

    assert result.allowed is True
    assert result.status == BudgetStatus.NORMAL
    assert result.current_count == _CAP - 3


def test_archived_skills_stop_counting_once_the_library_looks_full(governor: SkillBudgetGovernor) -> None:
    store = _store_with(_CAP)
    archived = {f"skill-{index}": _ARCHIVED for index in range(2)}

    with patch(_STORE_GETTER, return_value=store), patch(_LIFECYCLE, side_effect=_lifecycle_of(archived)):
        result = check_skill_budget_before_evolution(agent_id="agent-1", governor=governor)

    assert result.allowed is True
    assert result.current_count == _CAP - 2


def test_library_stays_full_while_every_record_is_an_installed_skill(governor: SkillBudgetGovernor) -> None:
    store = _store_with(_CAP)

    with patch(_STORE_GETTER, return_value=store):
        result = check_skill_budget_before_evolution(agent_id="agent-1", governor=governor)

    store.get_active_skills.assert_called_once_with(agent_id="agent-1")
    assert result.allowed is False
    assert result.status == BudgetStatus.FULL
    assert result.current_count == _CAP


@pytest.mark.asyncio
async def test_trigger_proceeds_without_a_notice_below_the_cap(model_cfg: MagicMock, governor: SkillBudgetGovernor) -> None:
    with (
        patch(_STORE_GETTER, return_value=_store_with(_CAP - 1)),
        patch(_RUN_TASK, new_callable=AsyncMock) as run_task,
        patch(_PUBLISH_NOTICE) as publish_notice,
    ):
        _trigger("chat-below-cap", model_cfg, governor)
        await asyncio.sleep(0)

    run_task.assert_called_once()
    publish_notice.assert_not_called()


@pytest.mark.asyncio
async def test_trigger_pauses_capture_and_tells_the_user_once_per_full_library(
    model_cfg: MagicMock, governor: SkillBudgetGovernor
) -> None:
    with (
        patch(_STORE_GETTER, return_value=_store_with(_CAP)),
        patch(_RUN_TASK, new_callable=AsyncMock) as run_task,
        patch(_PUBLISH_NOTICE) as publish_notice,
    ):
        _trigger("chat-full-1", model_cfg, governor, agent_id="agent-1")
        _trigger("chat-full-2", model_cfg, governor, agent_id="agent-1")
        await asyncio.sleep(0)

    run_task.assert_not_called()
    publish_notice.assert_called_once_with(agent_id="agent-1", current_count=_CAP, max_count=_CAP)


@pytest.mark.asyncio
async def test_notice_rearms_once_capacity_frees_up(model_cfg: MagicMock, governor: SkillBudgetGovernor) -> None:
    with (
        patch(_RUN_TASK, new_callable=AsyncMock) as run_task,
        patch(_PUBLISH_NOTICE) as publish_notice,
    ):
        with patch(_STORE_GETTER, return_value=_store_with(_CAP)):
            _trigger("chat-a", model_cfg, governor, agent_id="agent-1")
        with patch(_STORE_GETTER, return_value=_store_with(_CAP - 1)):
            _trigger("chat-b", model_cfg, governor, agent_id="agent-1")
            await asyncio.sleep(0)
        with patch(_STORE_GETTER, return_value=_store_with(_CAP)):
            _trigger("chat-c", model_cfg, governor, agent_id="agent-1")

    run_task.assert_called_once()
    assert publish_notice.call_count == 2


@pytest.mark.asyncio
async def test_each_agent_scope_is_told_about_its_own_full_library(model_cfg: MagicMock, governor: SkillBudgetGovernor) -> None:
    with (
        patch(_STORE_GETTER, return_value=_store_with(_CAP)),
        patch(_PUBLISH_NOTICE) as publish_notice,
    ):
        _trigger("chat-1", model_cfg, governor, agent_id="agent-1")
        _trigger("chat-2", model_cfg, governor, agent_id="agent-2")
        _trigger("chat-3", model_cfg, governor, agent_id=None)

    notified_agents = [call.kwargs["agent_id"] for call in publish_notice.call_args_list]
    assert notified_agents == ["agent-1", "agent-2", None]
