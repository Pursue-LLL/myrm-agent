"""Unit tests for PreFlightBudgetService."""

import pytest

from app.schemas.pre_flight_budget import (
    BudgetActionEnum,
    BudgetConfigCreateRequest,
    BudgetPeriodEnum,
    RecordSpendRequest,
)
from app.services.security.pre_flight_budget_service import PreFlightBudgetService


@pytest.fixture(autouse=True)
def clean_service() -> None:
    PreFlightBudgetService.reset_instance()


def test_service_config_lifecycle() -> None:
    service = PreFlightBudgetService.get_instance()

    req = BudgetConfigCreateRequest(
        project_id="proj_srv_1",
        limit_amount=25.0,
        currency="USD",
        period=BudgetPeriodEnum.DAILY,
        action=BudgetActionEnum.PAUSE,
    )
    cfg = service.set_config(req)
    assert cfg.project_id == "proj_srv_1"
    assert cfg.limit_amount == 25.0
    assert cfg.action == BudgetActionEnum.PAUSE

    retrieved = service.get_config("proj_srv_1")
    assert retrieved is not None
    assert retrieved.limit_amount == 25.0

    missing = service.get_config("proj_not_exist")
    assert missing is None


def test_service_spend_and_evaluation() -> None:
    service = PreFlightBudgetService.get_instance()

    service.set_config(
        BudgetConfigCreateRequest(
            project_id="proj_srv_2",
            limit_amount=10.0,
            currency="USD",
            period=BudgetPeriodEnum.DAILY,
            action=BudgetActionEnum.STOP,
        )
    )

    # Initial evaluation: no spend
    eval1 = service.evaluate("proj_srv_2")
    assert not eval1.tripped
    assert eval1.current_spend == 0.0

    # Record spend
    service.record_spend(
        RecordSpendRequest(
            project_id="proj_srv_2",
            amount=6.0,
            model_name="claude-3-5-sonnet",
        )
    )

    eval2 = service.evaluate("proj_srv_2")
    assert not eval2.tripped
    assert eval2.current_spend == 6.0

    # Record more spend to breach limit
    service.record_spend(
        RecordSpendRequest(
            project_id="proj_srv_2",
            amount=5.0,
            model_name="claude-3-5-sonnet",
        )
    )

    eval3 = service.evaluate("proj_srv_2")
    assert eval3.tripped
    assert eval3.current_spend == 11.0
    assert eval3.action == BudgetActionEnum.STOP


def test_service_queue_dispatch_lock() -> None:
    service = PreFlightBudgetService.get_instance()

    service.set_config(
        BudgetConfigCreateRequest(
            project_id="proj_srv_queue",
            limit_amount=5.0,
            currency="USD",
        )
    )

    allowed = service.is_queue_dispatch_allowed("proj_srv_queue")
    assert allowed.queue_dispatch_allowed

    # Breach
    service.record_spend(
        RecordSpendRequest(
            project_id="proj_srv_queue",
            amount=5.5,
        )
    )

    locked = service.is_queue_dispatch_allowed("proj_srv_queue")
    assert not locked.queue_dispatch_allowed
    assert "Queue locked" in locked.reason


def test_service_events_retrieval() -> None:
    service = PreFlightBudgetService.get_instance()

    service.set_config(
        BudgetConfigCreateRequest(
            project_id="proj_events",
            limit_amount=2.0,
        )
    )

    service.record_spend(
        RecordSpendRequest(
            project_id="proj_events",
            amount=1.0,
        )
    )

    events = service.get_events(project_id="proj_events")
    assert len(events) >= 1
    assert any(e.event_type == "spend_recorded" for e in events)
