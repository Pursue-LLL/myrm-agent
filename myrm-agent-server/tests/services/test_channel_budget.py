"""Unit tests for per-channel budget quota enforcement.

Covers ChannelBudgetRegistry, ChannelBudgetPolicy, should_block_channel,
record_channel_cost, and _build_status_dict.
"""

from __future__ import annotations

from myrm_agent_harness.utils.token_economics.budget_guard import BudgetStatus

from app.services.budget.channel_budget import (
    ChannelBudgetPolicy,
    ChannelBudgetRegistry,
    record_channel_cost,
    should_block_channel,
)


class TestChannelBudgetPolicy:
    def test_defaults(self) -> None:
        p = ChannelBudgetPolicy(channel_key="telegram:group:chat-1")
        assert p.daily_limit_usd == 2.0
        assert p.warning_threshold == 0.8
        assert p.enabled is True
        assert p.label == ""

    def test_custom_values(self) -> None:
        p = ChannelBudgetPolicy(
            channel_key="slack:group:C123",
            daily_limit_usd=5.0,
            warning_threshold=0.7,
            enabled=False,
            label="Team Chat",
        )
        assert p.daily_limit_usd == 5.0
        assert p.warning_threshold == 0.7
        assert p.enabled is False
        assert p.label == "Team Chat"


class TestChannelBudgetRegistry:
    def _make_registry(self) -> ChannelBudgetRegistry:
        return ChannelBudgetRegistry()

    def test_check_budget_returns_ok_for_unknown_channel(self) -> None:
        reg = self._make_registry()
        assert reg.check_budget("nonexistent") == BudgetStatus.OK

    def test_record_cost_returns_ok_for_unknown_channel(self) -> None:
        reg = self._make_registry()
        assert reg.record_cost("nonexistent", 1.0) == BudgetStatus.OK

    def test_configure_enabled_creates_guard(self) -> None:
        reg = self._make_registry()
        policy = ChannelBudgetPolicy(channel_key="ch:1", daily_limit_usd=1.0)
        reg.configure(policy)
        assert reg.check_budget("ch:1") == BudgetStatus.OK

    def test_configure_disabled_removes_guard(self) -> None:
        reg = self._make_registry()
        reg.configure(ChannelBudgetPolicy(channel_key="ch:1", daily_limit_usd=1.0))
        reg.configure(ChannelBudgetPolicy(channel_key="ch:1", enabled=False))
        assert reg.check_budget("ch:1") == BudgetStatus.OK

    def test_record_cost_triggers_warning(self) -> None:
        reg = self._make_registry()
        reg.configure(ChannelBudgetPolicy(
            channel_key="ch:w",
            daily_limit_usd=1.0,
            warning_threshold=0.5,
        ))
        status = reg.record_cost("ch:w", 0.6)
        assert status == BudgetStatus.WARNING

    def test_record_cost_triggers_exceeded(self) -> None:
        reg = self._make_registry()
        reg.configure(ChannelBudgetPolicy(
            channel_key="ch:e",
            daily_limit_usd=1.0,
        ))
        reg.record_cost("ch:e", 0.5)
        status = reg.record_cost("ch:e", 0.6)
        assert status == BudgetStatus.EXCEEDED

    def test_check_budget_exceeded_after_recording(self) -> None:
        reg = self._make_registry()
        reg.configure(ChannelBudgetPolicy(channel_key="ch:x", daily_limit_usd=0.5))
        reg.record_cost("ch:x", 0.6)
        assert reg.check_budget("ch:x") == BudgetStatus.EXCEEDED

    def test_remove_clears_guard_and_policy(self) -> None:
        reg = self._make_registry()
        reg.configure(ChannelBudgetPolicy(channel_key="ch:r", daily_limit_usd=1.0))
        reg.remove("ch:r")
        assert reg.check_budget("ch:r") == BudgetStatus.OK
        assert reg.get_status("ch:r") is None

    def test_get_status_returns_none_for_unknown(self) -> None:
        reg = self._make_registry()
        assert reg.get_status("nope") is None

    def test_get_status_enabled(self) -> None:
        reg = self._make_registry()
        reg.configure(ChannelBudgetPolicy(
            channel_key="ch:s",
            daily_limit_usd=2.0,
            label="Test",
        ))
        st = reg.get_status("ch:s")
        assert st is not None
        assert st["channel_key"] == "ch:s"
        assert st["label"] == "Test"
        assert st["enabled"] is True
        assert st["daily_limit_usd"] == 2.0
        assert st["today_cost_usd"] == 0.0
        assert st["status"] == "ok"

    def test_get_status_disabled(self) -> None:
        reg = self._make_registry()
        reg.configure(ChannelBudgetPolicy(
            channel_key="ch:d",
            enabled=False,
            label="Off",
        ))
        st = reg.get_status("ch:d")
        assert st is not None
        assert st["enabled"] is False
        assert st["status"] == "disabled"

    def test_get_all_statuses_sorted(self) -> None:
        reg = self._make_registry()
        reg.configure(ChannelBudgetPolicy(channel_key="b:ch", daily_limit_usd=1.0))
        reg.configure(ChannelBudgetPolicy(channel_key="a:ch", daily_limit_usd=2.0))
        all_st = reg.get_all_statuses()
        assert len(all_st) == 2
        assert all_st[0]["channel_key"] == "a:ch"
        assert all_st[1]["channel_key"] == "b:ch"

    def test_get_all_statuses_empty(self) -> None:
        reg = self._make_registry()
        assert reg.get_all_statuses() == []

    def test_policies_property_returns_copy(self) -> None:
        reg = self._make_registry()
        reg.configure(ChannelBudgetPolicy(channel_key="ch:p", daily_limit_usd=3.0))
        policies = reg.policies
        assert "ch:p" in policies
        policies.pop("ch:p")
        assert "ch:p" in reg.policies

    def test_configure_with_initial_cost(self) -> None:
        reg = self._make_registry()
        reg.configure(
            ChannelBudgetPolicy(channel_key="ch:ic", daily_limit_usd=1.0),
            initial_cost=0.9,
        )
        st = reg.get_status("ch:ic")
        assert st is not None
        assert st["today_cost_usd"] > 0.8

    def test_usage_pct_calculation(self) -> None:
        reg = self._make_registry()
        reg.configure(
            ChannelBudgetPolicy(channel_key="ch:pct", daily_limit_usd=10.0),
            initial_cost=5.0,
        )
        st = reg.get_status("ch:pct")
        assert st is not None
        assert st["usage_pct"] == 50.0

    def test_usage_pct_zero_limit(self) -> None:
        """Edge case: policy with minimum limit."""
        reg = self._make_registry()
        reg.configure(
            ChannelBudgetPolicy(channel_key="ch:zl", daily_limit_usd=0.01),
            initial_cost=0.0,
        )
        st = reg.get_status("ch:zl")
        assert st is not None
        assert isinstance(st["usage_pct"], float)


class TestShouldBlockChannel:
    def test_returns_false_for_unconfigured_channel(self) -> None:
        assert should_block_channel("unknown:channel") is False

    def test_returns_false_when_budget_ok(self, monkeypatch: object) -> None:
        from app.services.budget import channel_budget as mod

        reg = ChannelBudgetRegistry()
        reg.configure(ChannelBudgetPolicy(channel_key="ch:ok", daily_limit_usd=10.0))
        monkeypatch.setattr(mod, "_registry", reg)  # type: ignore[attr-defined]

        assert should_block_channel("ch:ok") is False

    def test_returns_true_when_budget_exceeded(self, monkeypatch: object) -> None:
        from app.services.budget import channel_budget as mod

        reg = ChannelBudgetRegistry()
        reg.configure(ChannelBudgetPolicy(channel_key="ch:ex", daily_limit_usd=0.5))
        reg.record_cost("ch:ex", 0.6)
        monkeypatch.setattr(mod, "_registry", reg)  # type: ignore[attr-defined]

        assert should_block_channel("ch:ex") is True


class TestRecordChannelCost:
    def test_noop_for_zero_cost(self, monkeypatch: object) -> None:
        from app.services.budget import channel_budget as mod

        reg = ChannelBudgetRegistry()
        reg.configure(ChannelBudgetPolicy(channel_key="ch:z", daily_limit_usd=1.0))
        monkeypatch.setattr(mod, "_registry", reg)  # type: ignore[attr-defined]

        record_channel_cost("ch:z", 0.0)
        st = reg.get_status("ch:z")
        assert st is not None
        assert st["today_cost_usd"] == 0.0

    def test_noop_for_negative_cost(self, monkeypatch: object) -> None:
        from app.services.budget import channel_budget as mod

        reg = ChannelBudgetRegistry()
        reg.configure(ChannelBudgetPolicy(channel_key="ch:n", daily_limit_usd=1.0))
        monkeypatch.setattr(mod, "_registry", reg)  # type: ignore[attr-defined]

        record_channel_cost("ch:n", -1.0)
        st = reg.get_status("ch:n")
        assert st is not None
        assert st["today_cost_usd"] == 0.0

    def test_records_positive_cost(self, monkeypatch: object) -> None:
        from app.services.budget import channel_budget as mod

        reg = ChannelBudgetRegistry()
        reg.configure(ChannelBudgetPolicy(channel_key="ch:rc", daily_limit_usd=5.0))
        monkeypatch.setattr(mod, "_registry", reg)  # type: ignore[attr-defined]

        record_channel_cost("ch:rc", 1.5)
        st = reg.get_status("ch:rc")
        assert st is not None
        assert st["today_cost_usd"] > 1.4
