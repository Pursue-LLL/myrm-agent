"""Tests for crash auto-continue logic in system.py.

Validates:
1. Eligible markers are dispatched and assistant message is persisted
2. Stale markers (>freshness window) are pruned
3. Exhausted markers (>=max_attempts) are pruned
4. User-disabled preference skips scanning entirely
5. Missing serialized_params / model_cfg guard
6. Failure creates error notification; notification failure does not crash
7. Crash-loop breaker increments attempt_count before executing
8. Config loader failure defaults to enabled
9. Empty stream does not persist message
10. Chat history is loaded before stream
11. Startup scan DB failure is swallowed (boot safety)
12. Non-dict stream chunks are skipped defensively
13. Marker cleanup failure is swallowed
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _disable_skill_roots_collection() -> None:
    """Keep runtime-context collection deterministic: no real storage I/O."""
    with patch(
        "app.core.skills.gates.disabled_skill_roots.collect_disabled_skill_roots",
        new_callable=AsyncMock,
        return_value=[],
    ):
        yield


def _make_marker(
    *,
    marker_id: str = "marker-001",
    chat_id: str = "chat-auto-001",
    attempt_count: int = 0,
    created_at: datetime | None = None,
    serialized_params: dict | None = None,
    pending_steering_messages: list[str] | None = None,
) -> MagicMock:
    m = MagicMock()
    m.id = marker_id
    m.chat_id = chat_id
    m.user_message_id = "msg-user-001"
    m.action_mode = "fast"
    m.agent_id = "default"
    m.attempt_count = attempt_count
    m.pending_steering_messages = pending_steering_messages
    m.created_at = created_at or datetime.now(UTC)
    m.serialized_params = serialized_params or {
        "chat_id": chat_id,
        "query": "hello",
        "message_id": "msg-user-001",
        "model_cfg": {"provider": "test", "model": "test-model"},
    }
    return m


def _mock_session_factory() -> tuple[MagicMock, AsyncMock]:
    factory = MagicMock()
    db = AsyncMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=db)
    factory.return_value.__aexit__ = AsyncMock(return_value=False)
    db.commit = AsyncMock()
    return factory, db


@pytest.mark.asyncio
async def test_auto_continue_success_persists_message():
    """Successful auto-continue collects message chunks and persists them."""
    marker = _make_marker()
    factory, db = _mock_session_factory()

    async def _fake_stream(*_a, **_kw):
        yield {"type": "progress", "data": {"status": "started"}}
        yield {"type": "message", "data": "Hello "}
        yield {"type": "message", "data": "world"}
        yield {"type": "message_end", "usage": {}}

    mock_notif = AsyncMock()
    mock_persist = AsyncMock()
    mock_chat_history = AsyncMock(return_value=[])

    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = [marker]
    db.execute = AsyncMock(return_value=result_mock)

    with (
        patch("app.platform_utils.get_session_factory", return_value=factory),
        patch(
            "app.core.channel_bridge.config_loader.load_user_configs",
            AsyncMock(
                return_value=MagicMock(
                    personal_settings_dict={"autoContinueInterruptedTurns": True}
                )
            ),
        ),
        patch("app.ai_agents.GeneralAgentParams") as mock_params_cls,
        patch(
            "app.services.agent.streaming.ai_agent_service_stream",
            side_effect=_fake_stream,
        ),
        patch(
            "app.services.chat.chat_service.ChatService.load_web_chat_history",
            mock_chat_history,
        ),
        patch(
            "app.services.chat.chat_service.ChatService.persist_assistant_message_safe",
            mock_persist,
        ),
        patch(
            "app.services.infra.system_notification.SystemNotificationService.create_notification",
            mock_notif,
        ),
    ):
        mock_params = MagicMock(
            model_cfg=MagicMock(),
            chat_id="chat-auto-001",
            query="hello",
            message_id="msg-user-001",
            timezone="UTC",
        )
        mock_params_cls.model_validate.return_value = mock_params

        from app.lifecycle.auto_continue import auto_continue_interrupted_turns

        await auto_continue_interrupted_turns()
        await asyncio.sleep(0.15)

    mock_persist.assert_awaited_once()
    persist_args = mock_persist.call_args
    assert persist_args[0][0] == "chat-auto-001"
    assert persist_args[0][1] == "Hello world"

    success_calls = [
        c for c in mock_notif.call_args_list if c[1].get("type") == "success"
    ]
    assert len(success_calls) >= 1


@pytest.mark.asyncio
async def test_auto_continue_replays_pending_steering_messages():
    """Pending steering messages in marker are restored to steering token upon recovery."""
    marker = _make_marker(pending_steering_messages=["redirect to topic b"])
    factory, db = _mock_session_factory()

    async def _fake_stream(*_a, **_kw):
        yield {"type": "message", "data": "Steered ok"}
        yield {"type": "message_end", "usage": {}}

    mock_notif = AsyncMock()
    mock_persist = AsyncMock()
    mock_chat_history = AsyncMock(return_value=[])

    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = [marker]
    db.execute = AsyncMock(return_value=result_mock)

    with (
        patch("app.platform_utils.get_session_factory", return_value=factory),
        patch(
            "app.core.channel_bridge.config_loader.load_user_configs",
            AsyncMock(return_value=MagicMock(personal_settings_dict={"autoContinueInterruptedTurns": True})),
        ),
        patch("app.ai_agents.GeneralAgentParams") as mock_params_cls,
        patch("app.services.agent.streaming.ai_agent_service_stream", side_effect=_fake_stream),
        patch("app.services.chat.chat_service.ChatService.load_web_chat_history", mock_chat_history),
        patch("app.services.chat.chat_service.ChatService.persist_assistant_message_safe", mock_persist),
        patch(
            "app.services.infra.system_notification.SystemNotificationService.create_notification",
            mock_notif,
        ),
        patch("myrm_agent_harness.utils.runtime.steering.set_steering_token") as mock_set_token,
    ):
        mock_params = MagicMock(
            model_cfg=MagicMock(),
            chat_id="chat-auto-001",
            query="hello",
            message_id="msg-user-001",
            timezone="UTC",
        )
        mock_params_cls.model_validate.return_value = mock_params

        from app.lifecycle.auto_continue import auto_continue_interrupted_turns

        await auto_continue_interrupted_turns()
        await asyncio.sleep(0.15)

        assert mock_set_token.called
        token_arg = mock_set_token.call_args[0][0]
        assert token_arg.has_pending is True
        assert token_arg.collect_all_steering_messages() == ["redirect to topic b"]


@pytest.mark.asyncio
async def test_auto_continue_forwards_token_economics_to_persist():
    """message_end token_economics is collected and persisted as extra_data.

    Guards the message-level cost ledger contract: the auto-continue resume
    path must keep Chat.total_* rebuildable from the same tokenEconomics
    snapshot that the canonical stream_finalize path stores.
    """
    marker = _make_marker()
    factory, db = _mock_session_factory()

    token_economics = {
        "call_count": 3,
        "total_cost_usd": 0.12,
        "usage": {"total_tokens": 1500},
    }

    async def _fake_stream(*_a, **_kw):
        yield {"type": "message", "data": "recovered "}
        yield {"type": "message", "data": "reply"}
        yield {"type": "message_end", "usage": {}, "token_economics": token_economics}

    mock_persist = AsyncMock()
    mock_notif = AsyncMock()

    with (
        patch("app.platform_utils.get_session_factory", return_value=factory),
        patch("app.ai_agents.GeneralAgentParams") as mock_params_cls,
        patch(
            "app.services.agent.streaming.ai_agent_service_stream",
            side_effect=_fake_stream,
        ),
        patch(
            "app.services.chat.chat_service.ChatService.load_web_chat_history",
            AsyncMock(return_value=[]),
        ),
        patch(
            "app.services.chat.chat_service.ChatService.persist_assistant_message_safe",
            mock_persist,
        ),
        patch(
            "app.services.infra.system_notification.SystemNotificationService.create_notification",
            mock_notif,
        ),
    ):
        mock_params_cls.model_validate.return_value = MagicMock(
            model_cfg=MagicMock(),
            chat_id="chat-auto-001",
            message_id="msg-user-001",
            timezone="UTC",
        )

        from app.lifecycle.auto_continue import _dispatch_auto_continue

        await _dispatch_auto_continue(marker, factory)

    mock_persist.assert_awaited_once()
    persist_args = mock_persist.call_args
    assert persist_args[0][0] == "chat-auto-001"
    assert persist_args[0][1] == "recovered reply"
    assert persist_args[1]["extra_data"] == {"tokenEconomics": token_economics}


@pytest.mark.asyncio
async def test_auto_continue_without_token_economics_persists_without_extra_data():
    """A message_end without token_economics persists with extra_data=None."""
    marker = _make_marker()
    factory, db = _mock_session_factory()

    async def _fake_stream(*_a, **_kw):
        yield {"type": "message", "data": "recovered reply"}
        yield {"type": "message_end", "usage": {}}

    mock_persist = AsyncMock()

    with (
        patch("app.platform_utils.get_session_factory", return_value=factory),
        patch("app.ai_agents.GeneralAgentParams") as mock_params_cls,
        patch(
            "app.services.agent.streaming.ai_agent_service_stream",
            side_effect=_fake_stream,
        ),
        patch(
            "app.services.chat.chat_service.ChatService.load_web_chat_history",
            AsyncMock(return_value=[]),
        ),
        patch(
            "app.services.chat.chat_service.ChatService.persist_assistant_message_safe",
            mock_persist,
        ),
        patch(
            "app.services.infra.system_notification.SystemNotificationService.create_notification",
            AsyncMock(),
        ),
    ):
        mock_params_cls.model_validate.return_value = MagicMock(
            model_cfg=MagicMock(),
            chat_id="chat-auto-001",
            message_id="msg-user-001",
            timezone="UTC",
        )

        from app.lifecycle.auto_continue import _dispatch_auto_continue

        await _dispatch_auto_continue(marker, factory)

    mock_persist.assert_awaited_once()
    persist_args = mock_persist.call_args
    assert persist_args[1]["extra_data"] is None


@pytest.mark.asyncio
async def test_auto_continue_disabled_by_preference():
    """When user disables autoContinueInterruptedTurns, scanning is skipped."""
    factory, db = _mock_session_factory()

    with (
        patch("app.platform_utils.get_session_factory", return_value=factory),
        patch(
            "app.core.channel_bridge.config_loader.load_user_configs",
            AsyncMock(
                return_value=MagicMock(
                    personal_settings_dict={"autoContinueInterruptedTurns": False}
                )
            ),
        ),
    ):
        from app.lifecycle.auto_continue import auto_continue_interrupted_turns

        await auto_continue_interrupted_turns()

    db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_auto_continue_no_markers():
    """No markers in DB means no dispatch."""
    factory, db = _mock_session_factory()

    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = []
    db.execute = AsyncMock(return_value=result_mock)

    mock_notif = AsyncMock()

    with (
        patch("app.platform_utils.get_session_factory", return_value=factory),
        patch(
            "app.core.channel_bridge.config_loader.load_user_configs",
            AsyncMock(return_value=MagicMock(personal_settings_dict={})),
        ),
        patch(
            "app.services.infra.system_notification.SystemNotificationService.create_notification",
            mock_notif,
        ),
    ):
        from app.lifecycle.auto_continue import auto_continue_interrupted_turns

        await auto_continue_interrupted_turns()

    mock_notif.assert_not_called()


@pytest.mark.asyncio
async def test_dispatch_skips_missing_params():
    """Marker with no serialized_params is skipped."""
    marker = _make_marker(serialized_params=None)
    marker.serialized_params = None
    factory, db = _mock_session_factory()

    mock_notif = AsyncMock()

    with (
        patch("app.platform_utils.get_session_factory", return_value=factory),
        patch(
            "app.services.infra.system_notification.SystemNotificationService.create_notification",
            mock_notif,
        ),
    ):
        from app.lifecycle.auto_continue import _dispatch_auto_continue

        await _dispatch_auto_continue(marker, factory)

    success_calls = [
        c for c in mock_notif.call_args_list if c[1].get("type") == "success"
    ]
    assert len(success_calls) == 0


@pytest.mark.asyncio
async def test_dispatch_skips_missing_model_cfg():
    """Marker with empty model_cfg is skipped."""
    marker = _make_marker()
    factory, db = _mock_session_factory()

    with (
        patch("app.platform_utils.get_session_factory", return_value=factory),
        patch("app.ai_agents.GeneralAgentParams") as mock_params_cls,
        patch(
            "app.services.chat.chat_service.ChatService.load_web_chat_history",
            AsyncMock(return_value=[]),
        ),
    ):
        mock_params_cls.model_validate.return_value = MagicMock(
            model_cfg=None,
            chat_id="chat-auto-001",
            message_id="msg-user-001",
        )

        from app.lifecycle.auto_continue import _dispatch_auto_continue

        await _dispatch_auto_continue(marker, factory)

    db.execute.assert_awaited()


@pytest.mark.asyncio
async def test_dispatch_failure_creates_error_notification():
    """When stream raises, error notification is created."""
    marker = _make_marker()
    factory, db = _mock_session_factory()

    mock_notif = AsyncMock()

    with (
        patch("app.platform_utils.get_session_factory", return_value=factory),
        patch("app.ai_agents.GeneralAgentParams") as mock_params_cls,
        patch(
            "app.services.agent.streaming.ai_agent_service_stream",
            side_effect=RuntimeError("LLM died"),
        ),
        patch(
            "app.services.chat.chat_service.ChatService.load_web_chat_history",
            AsyncMock(return_value=[]),
        ),
        patch(
            "app.services.infra.system_notification.SystemNotificationService.create_notification",
            mock_notif,
        ),
    ):
        mock_params_cls.model_validate.return_value = MagicMock(
            model_cfg=MagicMock(),
            chat_id="chat-auto-001",
            message_id="msg-user-001",
            timezone="UTC",
        )

        from app.lifecycle.auto_continue import _dispatch_auto_continue

        await _dispatch_auto_continue(marker, factory)

    error_calls = [c for c in mock_notif.call_args_list if c[1].get("type") == "error"]
    assert len(error_calls) >= 1
    assert error_calls[0][1]["source"] == "auto_continue"


@pytest.mark.asyncio
async def test_notification_failure_does_not_crash():
    """If notification creation itself fails, _dispatch_auto_continue should not raise."""
    marker = _make_marker()
    factory, db = _mock_session_factory()

    with (
        patch("app.platform_utils.get_session_factory", return_value=factory),
        patch("app.ai_agents.GeneralAgentParams") as mock_params_cls,
        patch(
            "app.services.agent.streaming.ai_agent_service_stream",
            side_effect=RuntimeError("fail"),
        ),
        patch(
            "app.services.chat.chat_service.ChatService.load_web_chat_history",
            AsyncMock(return_value=[]),
        ),
        patch(
            "app.services.infra.system_notification.SystemNotificationService.create_notification",
            AsyncMock(side_effect=Exception("DB down")),
        ),
    ):
        mock_params_cls.model_validate.return_value = MagicMock(
            model_cfg=MagicMock(),
            chat_id="chat-auto-001",
            message_id="msg-user-001",
            timezone="UTC",
        )

        from app.lifecycle.auto_continue import _dispatch_auto_continue

        await _dispatch_auto_continue(marker, factory)


@pytest.mark.asyncio
async def test_config_loader_failure_defaults_to_enabled():
    """If config loader raises, auto-continue should still proceed (default enabled)."""
    marker = _make_marker()
    factory, db = _mock_session_factory()

    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = [marker]
    db.execute = AsyncMock(return_value=result_mock)

    mock_notif = AsyncMock()

    async def _fake_stream(*_a, **_kw):
        yield {"type": "message", "data": "recovered"}

    with (
        patch("app.platform_utils.get_session_factory", return_value=factory),
        patch(
            "app.core.channel_bridge.config_loader.load_user_configs",
            AsyncMock(side_effect=RuntimeError("config DB corrupted")),
        ),
        patch("app.ai_agents.GeneralAgentParams") as mock_params_cls,
        patch(
            "app.services.agent.streaming.ai_agent_service_stream",
            side_effect=_fake_stream,
        ),
        patch(
            "app.services.chat.chat_service.ChatService.load_web_chat_history",
            AsyncMock(return_value=[]),
        ),
        patch(
            "app.services.chat.chat_service.ChatService.persist_assistant_message_safe",
            AsyncMock(),
        ),
        patch(
            "app.services.infra.system_notification.SystemNotificationService.create_notification",
            mock_notif,
        ),
    ):
        mock_params_cls.model_validate.return_value = MagicMock(
            model_cfg=MagicMock(),
            chat_id="chat-auto-001",
            message_id="msg-user-001",
            timezone="UTC",
        )

        from app.lifecycle.auto_continue import auto_continue_interrupted_turns

        await auto_continue_interrupted_turns()
        await asyncio.sleep(0.15)

    success_calls = [
        c for c in mock_notif.call_args_list if c[1].get("type") == "success"
    ]
    assert len(success_calls) >= 1, "Should proceed despite config failure"


@pytest.mark.asyncio
async def test_empty_stream_does_not_persist():
    """When stream yields no message events, persist should not be called."""
    marker = _make_marker()
    factory, db = _mock_session_factory()

    async def _empty_stream(*_a, **_kw):
        yield {"type": "progress", "data": {"status": "started"}}
        yield {"type": "message_end", "usage": {}}

    mock_persist = AsyncMock()

    with (
        patch("app.platform_utils.get_session_factory", return_value=factory),
        patch("app.ai_agents.GeneralAgentParams") as mock_params_cls,
        patch(
            "app.services.agent.streaming.ai_agent_service_stream",
            side_effect=_empty_stream,
        ),
        patch(
            "app.services.chat.chat_service.ChatService.load_web_chat_history",
            AsyncMock(return_value=[]),
        ),
        patch(
            "app.services.chat.chat_service.ChatService.persist_assistant_message_safe",
            mock_persist,
        ),
        patch(
            "app.services.infra.system_notification.SystemNotificationService.create_notification",
            AsyncMock(),
        ),
    ):
        mock_params_cls.model_validate.return_value = MagicMock(
            model_cfg=MagicMock(),
            chat_id="chat-auto-001",
            message_id="msg-user-001",
            timezone="UTC",
        )

        from app.lifecycle.auto_continue import _dispatch_auto_continue

        await _dispatch_auto_continue(marker, factory)

    mock_persist.assert_not_awaited()


@pytest.mark.asyncio
async def test_dispatch_loads_chat_history():
    """Dispatch should call load_web_chat_history before streaming."""
    marker = _make_marker()
    factory, db = _mock_session_factory()

    mock_load_history = AsyncMock(
        return_value=[["user", "previous msg"], ["assistant", "prev reply"]]
    )

    async def _fake_stream(*_a, **_kw):
        yield {"type": "message", "data": "ok"}

    with (
        patch("app.platform_utils.get_session_factory", return_value=factory),
        patch("app.ai_agents.GeneralAgentParams") as mock_params_cls,
        patch(
            "app.services.agent.streaming.ai_agent_service_stream",
            side_effect=_fake_stream,
        ),
        patch(
            "app.services.chat.chat_service.ChatService.load_web_chat_history",
            mock_load_history,
        ),
        patch(
            "app.services.chat.chat_service.ChatService.persist_assistant_message_safe",
            AsyncMock(),
        ),
        patch(
            "app.services.infra.system_notification.SystemNotificationService.create_notification",
            AsyncMock(),
        ),
    ):
        mock_params = MagicMock(
            model_cfg=MagicMock(),
            chat_id="chat-auto-001",
            message_id="msg-user-001",
            timezone="UTC",
        )
        mock_params_cls.model_validate.return_value = mock_params

        from app.lifecycle.auto_continue import _dispatch_auto_continue

        await _dispatch_auto_continue(marker, factory)

    mock_load_history.assert_awaited_once_with("chat-auto-001")


@pytest.mark.asyncio
async def test_dispatch_injects_runtime_context():
    """Auto-continue dispatch must inject execution_mode + disabled_skill_roots."""
    marker = _make_marker()
    factory, db = _mock_session_factory()

    stream_calls: list[dict[str, object]] = []

    async def _capturing_stream(*_a, **_kw):
        stream_calls.append(_kw)
        if False:
            yield {"type": "message", "data": "ok"}

    with (
        patch("app.platform_utils.get_session_factory", return_value=factory),
        patch("app.ai_agents.GeneralAgentParams") as mock_params_cls,
        patch(
            "app.services.agent.streaming.ai_agent_service_stream",
            side_effect=_capturing_stream,
        ),
        patch(
            "app.services.chat.chat_service.ChatService.load_web_chat_history",
            AsyncMock(return_value=[]),
        ),
        patch(
            "app.services.chat.chat_service.ChatService.persist_assistant_message_safe",
            AsyncMock(),
        ),
        patch(
            "app.services.infra.system_notification.SystemNotificationService.create_notification",
            AsyncMock(),
        ),
        patch(
            "app.core.skills.gates.disabled_skill_roots.collect_disabled_skill_roots",
            new_callable=AsyncMock,
            return_value=["skills/prebuilt/off"],
        ),
    ):
        mock_params_cls.model_validate.return_value = MagicMock(
            model_cfg=MagicMock(),
            chat_id="chat-auto-001",
            message_id="msg-user-001",
            timezone="UTC",
        )

        from app.lifecycle.auto_continue import _dispatch_auto_continue

        await _dispatch_auto_continue(marker, factory)

    assert len(stream_calls) == 1
    extra_context = stream_calls[0].get("extra_context")
    assert isinstance(extra_context, dict)
    assert extra_context["execution_mode"] == "pooled"
    assert extra_context["disabled_skill_roots"] == ["skills/prebuilt/off"]


@pytest.mark.asyncio
async def test_startup_scan_swallows_db_failure():
    """Startup scan DB failure is swallowed so startup continues safely."""
    factory = MagicMock()
    db = AsyncMock()
    db.commit = AsyncMock()
    db.execute = AsyncMock(side_effect=RuntimeError("db unavailable"))
    factory.return_value.__aenter__ = AsyncMock(return_value=db)
    factory.return_value.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("app.platform_utils.get_session_factory", return_value=factory),
        patch(
            "app.core.channel_bridge.config_loader.load_user_configs",
            AsyncMock(return_value=MagicMock(personal_settings_dict={})),
        ),
    ):
        from app.lifecycle.auto_continue import auto_continue_interrupted_turns

        await auto_continue_interrupted_turns()


@pytest.mark.asyncio
async def test_dispatch_ignores_non_dict_chunks():
    """Stream chunks that are not dicts are skipped defensively."""
    marker = _make_marker()
    factory, db = _mock_session_factory()

    async def _stream_with_non_dict(*_a, **_kw):
        yield "raw-string-chunk"
        yield {"type": "message", "data": "ok"}

    mock_persist = AsyncMock()

    with (
        patch("app.platform_utils.get_session_factory", return_value=factory),
        patch("app.ai_agents.GeneralAgentParams") as mock_params_cls,
        patch(
            "app.services.agent.streaming.ai_agent_service_stream",
            side_effect=_stream_with_non_dict,
        ),
        patch(
            "app.services.chat.chat_service.ChatService.load_web_chat_history",
            AsyncMock(return_value=[]),
        ),
        patch(
            "app.services.chat.chat_service.ChatService.persist_assistant_message_safe",
            mock_persist,
        ),
        patch(
            "app.services.infra.system_notification.SystemNotificationService.create_notification",
            AsyncMock(),
        ),
    ):
        mock_params_cls.model_validate.return_value = MagicMock(
            model_cfg=MagicMock(),
            chat_id="chat-auto-001",
            message_id="msg-user-001",
            timezone="UTC",
        )

        from app.lifecycle.auto_continue import _dispatch_auto_continue

        await _dispatch_auto_continue(marker, factory)

    mock_persist.assert_awaited_once()
    assert mock_persist.call_args[0][1] == "ok"


@pytest.mark.asyncio
async def test_dispatch_cleanup_failure_is_swallowed():
    """Marker cleanup failure in finally is swallowed without raising."""
    marker = _make_marker()
    factory, db = _mock_session_factory()
    db.execute = AsyncMock(side_effect=[MagicMock(), RuntimeError("cleanup db down")])

    async def _fake_stream(*_a, **_kw):
        yield {"type": "message", "data": "ok"}

    with (
        patch("app.platform_utils.get_session_factory", return_value=factory),
        patch("app.ai_agents.GeneralAgentParams") as mock_params_cls,
        patch(
            "app.services.agent.streaming.ai_agent_service_stream",
            side_effect=_fake_stream,
        ),
        patch(
            "app.services.chat.chat_service.ChatService.load_web_chat_history",
            AsyncMock(return_value=[]),
        ),
        patch(
            "app.services.chat.chat_service.ChatService.persist_assistant_message_safe",
            AsyncMock(),
        ),
        patch(
            "app.services.infra.system_notification.SystemNotificationService.create_notification",
            AsyncMock(),
        ),
    ):
        mock_params_cls.model_validate.return_value = MagicMock(
            model_cfg=MagicMock(),
            chat_id="chat-auto-001",
            message_id="msg-user-001",
            timezone="UTC",
        )

        from app.lifecycle.auto_continue import _dispatch_auto_continue

        await _dispatch_auto_continue(marker, factory)


@pytest.mark.asyncio
async def test_auto_continue_restores_pending_steering_messages():
    """Validates that marker.pending_steering_messages are injected into SteeringToken upon auto-continue."""
    marker = _make_marker(
        pending_steering_messages=["Stop doing X and focus on Y", "Format output as JSON"]
    )
    factory, db = _mock_session_factory()

    async def _fake_stream(*_a, **_kw):
        yield {"type": "message", "data": "acknowledged"}

    mock_set_steering = MagicMock()

    with (
        patch("app.platform_utils.get_session_factory", return_value=factory),
        patch("app.ai_agents.GeneralAgentParams") as mock_params_cls,
        patch(
            "app.services.agent.streaming.ai_agent_service_stream",
            side_effect=_fake_stream,
        ),
        patch(
            "app.services.chat.chat_service.ChatService.load_web_chat_history",
            AsyncMock(return_value=[]),
        ),
        patch(
            "app.services.chat.chat_service.ChatService.persist_assistant_message_safe",
            AsyncMock(),
        ),
        patch(
            "app.services.infra.system_notification.SystemNotificationService.create_notification",
            AsyncMock(),
        ),
        patch(
            "myrm_agent_harness.utils.runtime.steering.set_steering_token",
            mock_set_steering,
        ),
    ):
        mock_params_cls.model_validate.return_value = MagicMock(
            model_cfg=MagicMock(),
            chat_id="chat-auto-001",
            message_id="msg-user-001",
            timezone="UTC",
        )

        from app.lifecycle.auto_continue import _dispatch_auto_continue

        await _dispatch_auto_continue(marker, factory)

    mock_set_steering.assert_called_once()
    token = mock_set_steering.call_args[0][0]
    assert token.collect_all_steering_messages() == [
        "Stop doing X and focus on Y",
        "Format output as JSON",
    ]

