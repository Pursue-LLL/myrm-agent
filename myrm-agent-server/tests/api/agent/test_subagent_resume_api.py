"""Tests for the subagent resume endpoint (POST /chats/{chat_id}/subagents/{task_id}/resume).

Verifies that resume failures (corrupted checkpoint / missing checkpoint) are
surfaced to the client with a real status instead of a detached-task false
success.
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from myrm_agent_harness.agent.sub_agents.checkpoint.saver import CheckpointCorruptedError

from app.api.agents.subagents import resume_subagent
from app.services.agent.gateway import get_agent_gateway


def _make_session_info(agent: object) -> SimpleNamespace:
    return SimpleNamespace(agent=lambda: agent)


def _fake_gateway(chat_id: str, agent: object) -> MagicMock:
    gateway = MagicMock()
    gateway._session_info = {chat_id: _make_session_info(agent)}
    return gateway


@pytest.mark.anyio
async def test_resume_returns_real_success(monkeypatch) -> None:
    manager = MagicMock()
    manager.resume_from_checkpoint = AsyncMock(return_value=None)
    agent = MagicMock()
    agent.subagent_manager = manager
    gateway = _fake_gateway("chat-1", agent)
    monkeypatch.setattr("app.api.agents.subagents.get_agent_gateway", lambda: gateway)

    resp = await resume_subagent("chat-1", "task-1")

    assert resp.status_code == 200
    body = json.loads(resp.body)
    assert body["success"] is True
    assert body["data"]["resumed"] is True


@pytest.mark.anyio
async def test_resume_surfaces_corrupted_checkpoint_as_400(monkeypatch) -> None:
    manager = MagicMock()
    manager.resume_from_checkpoint = AsyncMock(
        side_effect=CheckpointCorruptedError("checkpoint task-1 is corrupted")
    )
    agent = MagicMock()
    agent.subagent_manager = manager
    gateway = _fake_gateway("chat-1", agent)
    monkeypatch.setattr("app.api.agents.subagents.get_agent_gateway", lambda: gateway)

    resp = await resume_subagent("chat-1", "task-1")

    assert resp.status_code == 400
    body = json.loads(resp.body)
    assert body["success"] is False
    assert "corrupted" in body["message"]


@pytest.mark.anyio
async def test_resume_surfaces_missing_checkpoint_as_404(monkeypatch) -> None:
    manager = MagicMock()
    manager.resume_from_checkpoint = AsyncMock(
        side_effect=ValueError("No checkpoint found for task_id=task-1")
    )
    agent = MagicMock()
    agent.subagent_manager = manager
    gateway = _fake_gateway("chat-1", agent)
    monkeypatch.setattr("app.api.agents.subagents.get_agent_gateway", lambda: gateway)

    resp = await resume_subagent("chat-1", "task-1")

    assert resp.status_code == 404
    body = json.loads(resp.body)
    assert body["success"] is False


@pytest.mark.anyio
async def test_resume_surfaces_unknown_failure_as_500(monkeypatch) -> None:
    manager = MagicMock()
    manager.resume_from_checkpoint = AsyncMock(side_effect=RuntimeError("disk failure"))
    agent = MagicMock()
    agent.subagent_manager = manager
    gateway = _fake_gateway("chat-1", agent)
    monkeypatch.setattr("app.api.agents.subagents.get_agent_gateway", lambda: gateway)

    resp = await resume_subagent("chat-1", "task-1")

    assert resp.status_code == 500
    body = json.loads(resp.body)
    assert body["success"] is False


@pytest.mark.anyio
async def test_resume_requires_active_session(monkeypatch) -> None:
    gateway = _fake_gateway("chat-1", MagicMock())
    monkeypatch.setattr("app.api.agents.subagents.get_agent_gateway", lambda: gateway)

    resp = await resume_subagent("missing-chat", "task-1")

    assert resp.status_code == 400


def test_gateway_exists() -> None:
    assert get_agent_gateway() is not None
