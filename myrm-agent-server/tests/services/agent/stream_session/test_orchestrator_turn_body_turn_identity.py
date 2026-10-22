"""Regression: the turn body stamps the memo turn identity before the marker serialises params.

The identity used to be written before ``params`` was built, which raised ``UnboundLocalError``
on every persisted turn (``orchestrator_turn_body.py``). This test drives the real body with
the surrounding pipeline stubbed so the assignment point is what is exercised.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.agent.stream_session import (
    chat_history_bootstrap,
    orchestrator_turn_body,
    pre_reply_compact_sse,
)


@pytest.mark.asyncio
async def test_turn_identity_is_stamped_on_the_built_params(monkeypatch: pytest.MonkeyPatch) -> None:
    persisted = chat_history_bootstrap.BootstrappedMessageId("msg-persisted")
    params = SimpleNamespace(turn_identity=None)
    turn = SimpleNamespace(
        params=params,
        extra_context={},
        routing_tier=None,
        archive_restore_results=None,
        routing_specialty=None,
        routing_reason=None,
        context_warnings=None,
    )
    captured: dict[str, object] = {}
    pumped: list[object] = []

    async def fake_persist(*_args: object, **_kwargs: object) -> chat_history_bootstrap.BootstrappedMessageId:
        return persisted

    async def fake_history(*_args: object, **_kwargs: object) -> list[object]:
        return []

    async def fake_history_mode(*_args: object, **_kwargs: object) -> None:
        return None

    async def fake_apply_project(*_args: object, **_kwargs: object) -> None:
        return None

    async def fake_build_turn(*_args: object, **_kwargs: object) -> object:
        return turn

    async def fake_research_model(*_args: object, **_kwargs: object) -> None:
        return None

    def fake_unavailable(*_args: object, **_kwargs: object) -> None:
        return None

    async def fake_goal_provider(*_args: object, **_kwargs: object) -> None:
        return None

    async def fake_extra_context(*_args: object, base: object = None, **_kwargs: object) -> dict[str, object]:
        return dict(base or {})

    async def fake_compact(*_args: object, **_kwargs: object) -> None:
        return None

    async def fake_marker(_request: object, marker_params: object, *, user_message_id: object = None) -> None:
        captured["params"] = marker_params
        captured["user_message_id"] = user_message_id

    async def fake_pump(_session: object, _buffer: object) -> None:
        pumped.append(_session)

    monkeypatch.setattr(chat_history_bootstrap, "persist_user_message", fake_persist)
    monkeypatch.setattr(chat_history_bootstrap, "load_chat_history", fake_history)
    monkeypatch.setattr(orchestrator_turn_body, "resolve_turn_history_mode", fake_history_mode)
    monkeypatch.setattr(orchestrator_turn_body, "apply_migration_bound_project", fake_apply_project)
    monkeypatch.setattr(orchestrator_turn_body, "build_turn_params", fake_build_turn)
    monkeypatch.setattr(orchestrator_turn_body, "resolve_research_model", fake_research_model)
    monkeypatch.setattr(orchestrator_turn_body, "search_service_unavailable_detail", fake_unavailable)
    monkeypatch.setattr(orchestrator_turn_body, "prepare_goal_provider", fake_goal_provider)
    monkeypatch.setattr(orchestrator_turn_body, "build_turn_extra_context", fake_extra_context)
    monkeypatch.setattr(orchestrator_turn_body, "write_interrupted_turn_marker", fake_marker)
    monkeypatch.setattr(orchestrator_turn_body, "pump_to_buffer", fake_pump)
    monkeypatch.setattr(orchestrator_turn_body, "AgentStreamSession", lambda **_kwargs: SimpleNamespace())
    monkeypatch.setattr(pre_reply_compact_sse, "run_pre_reply_compact_with_sse", fake_compact)

    request = SimpleNamespace(
        message_id="msg-1",
        chat_id="chat-1",
        agent_id="agent-1",
        resume_value=None,
        engine_params=None,
        sibling_group_id=None,
        action_mode="agent",
    )

    async def record_failure(_reason: object) -> None:
        return None

    await orchestrator_turn_body.execute_agent_turn_after_reserve(
        request=request,
        http_request=SimpleNamespace(),
        text_content="hello",
        stream_started_at_monotonic=0.0,
        registry=SimpleNamespace(),
        buffer=SimpleNamespace(),
        record_terminal_failure=record_failure,
    )

    assert captured["params"] is params
    assert params.turn_identity == "msg-persisted"
    assert captured["user_message_id"] == persisted
    assert len(pumped) == 1
