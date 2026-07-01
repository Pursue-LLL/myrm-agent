"""Tests for budget enforcer — SSE event emission, guard lifecycle, and budget blocking."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.budget.enforcer import (
    BudgetPolicy,
    _BudgetGuardWrapper,
    _emit_budget_sse,
)
from app.services.event.app_event_bus import AppEventType, ServerEventBus


class TestEmitBudgetSse:
    """Verify _emit_budget_sse publishes correct AppEvent to EventBus."""

    def test_emits_warning_event(self) -> None:
        bus = ServerEventBus()
        q = bus.subscribe()

        with patch("app.services.event.app_event_bus.get_event_bus", return_value=bus):
            _emit_budget_sse("warning", cost=8.5, limit=10.0, dimension="daily")

        event = q.get_nowait()
        assert event.event_type == AppEventType.BUDGET_ALERT
        assert event.data["status"] == "warning"
        assert event.data["dimension"] == "daily"
        assert event.data["today_cost"] == 8.5
        assert event.data["daily_limit"] == 10.0
        assert event.data["remaining"] == 1.5
        assert event.data["pct"] == 85.0
        assert event.data["eco_mode"] is True

    def test_emits_exceeded_event(self) -> None:
        bus = ServerEventBus()
        q = bus.subscribe()

        with patch("app.services.event.app_event_bus.get_event_bus", return_value=bus):
            _emit_budget_sse("exceeded", cost=12.0, limit=10.0, dimension="per_session")

        event = q.get_nowait()
        assert event.event_type == AppEventType.BUDGET_ALERT
        assert event.data["status"] == "exceeded"
        assert event.data["dimension"] == "per_session"
        assert event.data["remaining"] == 0.0
        assert event.data["pct"] == 120.0
        assert event.data["eco_mode"] is True

    def test_ok_status_eco_mode_false(self) -> None:
        bus = ServerEventBus()
        q = bus.subscribe()

        with patch("app.services.event.app_event_bus.get_event_bus", return_value=bus):
            _emit_budget_sse("ok", cost=3.0, limit=10.0, dimension="daily")

        event = q.get_nowait()
        assert event.data["eco_mode"] is False

    def test_handles_zero_budget_gracefully(self) -> None:
        bus = ServerEventBus()
        q = bus.subscribe()

        with patch("app.services.event.app_event_bus.get_event_bus", return_value=bus):
            _emit_budget_sse("exceeded", cost=5.0, limit=0.0, dimension="daily")

        event = q.get_nowait()
        assert event.data["pct"] == 100.0

    def test_silent_on_exception(self) -> None:
        with patch("app.services.event.app_event_bus.get_event_bus", side_effect=RuntimeError("test")):
            _emit_budget_sse("warning", cost=1.0, limit=10.0, dimension="daily")


class TestBudgetPolicy:
    """Verify BudgetPolicy model validation."""

    def test_default_values(self) -> None:
        policy = BudgetPolicy()
        assert policy.enabled is False
        assert policy.daily_limit_usd == 10.0
        assert policy.warning_threshold == 0.8
        assert policy.action_on_exceeded == "finalize"

    def test_valid_block_action(self) -> None:
        policy = BudgetPolicy(enabled=True, action_on_exceeded="block")
        assert policy.action_on_exceeded == "block"

    def test_invalid_action_rejected(self) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            BudgetPolicy(action_on_exceeded="invalid")


class TestBudgetGuardWrapper:
    """Verify _BudgetGuardWrapper initializes correctly with initial_daily_cost."""

    def test_wrapper_passes_initial_cost(self) -> None:
        policy = BudgetPolicy(enabled=True, daily_limit_usd=10.0)
        wrapper = _BudgetGuardWrapper(policy, initial_daily_cost=5.0)
        assert wrapper.guard.daily_cost == 5.0
        assert wrapper.guard.daily_limit == 10.0

    def test_wrapper_zero_initial_cost(self) -> None:
        policy = BudgetPolicy(enabled=True, daily_limit_usd=20.0, warning_threshold=0.5)
        wrapper = _BudgetGuardWrapper(policy)
        assert wrapper.guard.daily_cost == 0.0

    def test_wrapper_emits_sse_on_warning(self) -> None:
        bus = ServerEventBus()
        q = bus.subscribe()
        policy = BudgetPolicy(
            enabled=True,
            daily_limit_usd=10.0,
            session_limit_usd=None,
            warning_threshold=0.8,
            finalization_reserve_pct=0.05,
        )

        with patch("app.services.event.app_event_bus.get_event_bus", return_value=bus):
            wrapper = _BudgetGuardWrapper(policy)
            wrapper.guard.record_cost(8.2)

        event = q.get_nowait()
        assert event.data["status"] == "warning"
        assert event.data["eco_mode"] is True

    def test_wrapper_emits_sse_on_exceeded(self) -> None:
        bus = ServerEventBus()
        q = bus.subscribe()
        policy = BudgetPolicy(enabled=True, daily_limit_usd=10.0, session_limit_usd=None)

        with patch("app.services.event.app_event_bus.get_event_bus", return_value=bus):
            wrapper = _BudgetGuardWrapper(policy)
            wrapper.guard.record_cost(12.0)

        event = q.get_nowait()
        assert event.data["status"] == "exceeded"
        assert event.data["eco_mode"] is True

    def test_wrapper_initial_cost_preserves_across_policy_change(self) -> None:
        """Simulates save_budget_policy carrying cost from old guard to new guard."""
        old_policy = BudgetPolicy(enabled=True, daily_limit_usd=10.0)
        old_wrapper = _BudgetGuardWrapper(old_policy, initial_daily_cost=0.0)
        old_wrapper.guard.record_cost(7.5)

        carry_cost = old_wrapper.guard.daily_cost
        new_policy = BudgetPolicy(enabled=True, daily_limit_usd=20.0)
        new_wrapper = _BudgetGuardWrapper(new_policy, initial_daily_cost=carry_cost)

        assert new_wrapper.guard.daily_cost == pytest.approx(7.5)
        assert new_wrapper.guard.daily_limit == 20.0


class TestSaveBudgetPolicyDbRecovery:
    """Verify enabling policy after disable loads today's spend from DB."""

    @pytest.mark.asyncio
    async def test_save_budget_policy_loads_today_cost_when_guard_was_cleared(
        self,
    ) -> None:
        from app.services.budget import enforcer

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()
        mock_session.add = MagicMock()

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_factory = MagicMock(return_value=mock_ctx)

        enforcer._guard_instance = None
        with (
            patch.object(enforcer, "_query_today_cost", new_callable=AsyncMock, return_value=4.2),
            patch(
                "app.services.budget.enforcer.get_session_factory",
                return_value=mock_factory,
            ),
        ):
            await enforcer.save_budget_policy(BudgetPolicy(enabled=True, daily_limit_usd=10.0, action_on_exceeded="block"))

        assert enforcer._guard_instance is not None
        assert enforcer._guard_instance.guard.daily_cost == pytest.approx(4.2)
        enforcer._guard_instance = None


class TestShouldBlockExecution:
    """Verify should_block_execution logic with mocked dependencies."""

    @pytest.mark.asyncio
    async def test_block_when_exceeded_and_block_policy(self) -> None:
        from myrm_agent_harness.utils.token_economics.budget_guard import BudgetStatus

        from app.services.budget import enforcer

        mock_guard = MagicMock()
        mock_guard.check_budget.return_value = BudgetStatus.EXCEEDED

        policy = BudgetPolicy(enabled=True, action_on_exceeded="block")

        with (
            patch.object(
                enforcer,
                "load_budget_policy",
                new_callable=AsyncMock,
                return_value=policy,
            ),
            patch.object(
                enforcer,
                "get_budget_guard",
                new_callable=AsyncMock,
                return_value=mock_guard,
            ),
        ):
            result = await enforcer.should_block_execution()
        assert result is True

    @pytest.mark.asyncio
    async def test_no_block_when_exceeded_and_warn_policy(self) -> None:
        from app.services.budget import enforcer

        policy = BudgetPolicy(enabled=True, action_on_exceeded="warn")

        with patch.object(enforcer, "load_budget_policy", new_callable=AsyncMock, return_value=policy):
            result = await enforcer.should_block_execution()
        assert result is False

    @pytest.mark.asyncio
    async def test_no_block_when_disabled(self) -> None:
        from app.services.budget import enforcer

        policy = BudgetPolicy(enabled=False)

        with patch.object(enforcer, "load_budget_policy", new_callable=AsyncMock, return_value=policy):
            result = await enforcer.should_block_execution()
        assert result is False

    @pytest.mark.asyncio
    async def test_no_block_when_under_budget(self) -> None:
        from myrm_agent_harness.utils.token_economics.budget_guard import BudgetStatus

        from app.services.budget import enforcer

        mock_guard = MagicMock()
        mock_guard.check_budget.return_value = BudgetStatus.OK

        policy = BudgetPolicy(enabled=True, action_on_exceeded="block")

        with (
            patch.object(
                enforcer,
                "load_budget_policy",
                new_callable=AsyncMock,
                return_value=policy,
            ),
            patch.object(
                enforcer,
                "get_budget_guard",
                new_callable=AsyncMock,
                return_value=mock_guard,
            ),
        ):
            result = await enforcer.should_block_execution()
        assert result is False

    @pytest.mark.asyncio
    async def test_no_block_when_guard_is_none(self) -> None:
        from app.services.budget import enforcer

        policy = BudgetPolicy(enabled=True, action_on_exceeded="block")

        with (
            patch.object(
                enforcer,
                "load_budget_policy",
                new_callable=AsyncMock,
                return_value=policy,
            ),
            patch.object(enforcer, "get_budget_guard", new_callable=AsyncMock, return_value=None),
        ):
            result = await enforcer.should_block_execution()
        assert result is False


class TestResetSessionBudget:
    """Verify reset_session_budget only resets on chat_id change."""

    def test_resets_on_new_chat_id(self) -> None:
        from app.services.budget import enforcer

        policy = BudgetPolicy(enabled=True, daily_limit_usd=10.0, session_limit_usd=5.0)
        enforcer._guard_instance = _BudgetGuardWrapper(policy)
        enforcer._current_session_chat_id = None

        enforcer._guard_instance.guard.record_cost(3.0)
        assert enforcer._guard_instance.guard.session_cost == 3.0

        enforcer.reset_session_budget(chat_id="chat-001")
        assert enforcer._guard_instance.guard.session_cost == 0.0

    def test_does_not_reset_same_chat_id(self) -> None:
        from app.services.budget import enforcer

        policy = BudgetPolicy(enabled=True, daily_limit_usd=10.0, session_limit_usd=5.0)
        enforcer._guard_instance = _BudgetGuardWrapper(policy)
        enforcer._current_session_chat_id = "chat-001"

        enforcer._guard_instance.guard.record_cost(2.0)

        enforcer.reset_session_budget(chat_id="chat-001")
        assert enforcer._guard_instance.guard.session_cost == 2.0

    def test_resets_on_different_chat_id(self) -> None:
        from app.services.budget import enforcer

        policy = BudgetPolicy(enabled=True, daily_limit_usd=10.0, session_limit_usd=5.0)
        enforcer._guard_instance = _BudgetGuardWrapper(policy)
        enforcer._current_session_chat_id = "chat-001"

        enforcer._guard_instance.guard.record_cost(2.0)

        enforcer.reset_session_budget(chat_id="chat-002")
        assert enforcer._guard_instance.guard.session_cost == 0.0
        assert enforcer._current_session_chat_id == "chat-002"

    def test_always_resets_when_chat_id_none(self) -> None:
        from app.services.budget import enforcer

        policy = BudgetPolicy(enabled=True, daily_limit_usd=10.0, session_limit_usd=5.0)
        enforcer._guard_instance = _BudgetGuardWrapper(policy)
        enforcer._current_session_chat_id = "chat-001"

        enforcer._guard_instance.guard.record_cost(2.0)

        enforcer.reset_session_budget(chat_id=None)
        assert enforcer._guard_instance.guard.session_cost == 0.0


class TestQueryTodayCost:
    """Verify _query_today_cost error handling."""

    @pytest.mark.asyncio
    async def test_returns_zero_on_db_error(self) -> None:
        from app.services.budget.enforcer import _query_today_cost

        with patch(
            "app.services.budget.enforcer.get_session_factory",
            side_effect=RuntimeError("db down"),
        ):
            result = await _query_today_cost()
        assert result == 0.0
