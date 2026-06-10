"""Tests for KanbanService singleton behavior."""

from __future__ import annotations

import pytest

from app.services.kanban.service import KanbanService
from app.services.kanban.service_core import KanbanServiceCore


@pytest.fixture(autouse=True)
def _reset_singleton() -> None:
    KanbanService._instance = None
    yield
    KanbanService._instance = None


def test_get_instance_returns_kanban_service() -> None:
    svc = KanbanService.get_instance()
    assert isinstance(svc, KanbanService)
    assert hasattr(svc, "create_board")
    assert hasattr(svc, "move_task")


def test_get_instance_is_singleton() -> None:
    first = KanbanService.get_instance()
    second = KanbanService.get_instance()
    assert first is second


def test_kanban_service_core_has_no_get_instance() -> None:
    assert not hasattr(KanbanServiceCore, "get_instance")
