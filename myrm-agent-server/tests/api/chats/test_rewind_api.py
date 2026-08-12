"""API integration tests for POST /api/v1/chats/{chat_id}/rewind."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import httpx
import pytest
from httpx import ASGITransport

from app.services.chat.session_continuity_service import ContinuitySyncError
from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="chats")


@pytest.fixture
async def async_client() -> httpx.AsyncClient:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers={"Content-Type": "application/json"},
        timeout=60.0,
    ) as client:
        yield client


async def _create_chat(chat_id: str) -> None:
    from app.database.models.chat import Chat
    from app.platform_utils import get_session_factory

    factory = get_session_factory()
    async with factory() as db:
        db.add(
            Chat(
                id=chat_id,
                title=f"Rewind Test {chat_id[:8]}",
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        )
        await db.commit()


async def _insert_messages(chat_id: str) -> dict[str, str]:
    from app.database.models.chat import Message
    from app.platform_utils import get_session_factory

    factory = get_session_factory()
    base_time = datetime.now(UTC) - timedelta(minutes=4)
    ids = {
        "u1": str(uuid.uuid4()),
        "a1": str(uuid.uuid4()),
        "u2": str(uuid.uuid4()),
        "a2": str(uuid.uuid4()),
    }
    contents = {
        "u1": "First question",
        "a1": "First answer",
        "u2": "Second question",
        "a2": "Second answer",
    }
    async with factory() as db:
        for index, key in enumerate(["u1", "a1", "u2", "a2"]):
            role = "user" if key.startswith("u") else "assistant"
            ts = base_time + timedelta(seconds=index * 10)
            db.add(
                Message(
                    id=ids[key],
                    chat_id=chat_id,
                    role=role,
                    content=contents[key],
                    sent_at=ts,
                    sent_timezone="UTC",
                    created_at=ts,
                )
            )
        await db.commit()
    return ids


@pytest.mark.asyncio
async def test_rewind_user_message_returns_composer_text(
    async_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chat_id = f"rewind-{uuid.uuid4().hex[:8]}"
    await _create_chat(chat_id)
    ids = await _insert_messages(chat_id)

    async def _fake_sync(_chat_id: str) -> int:
        return 2

    monkeypatch.setattr(
        "app.services.chat.session_continuity_service.sync_chat_checkpoint_from_db",
        _fake_sync,
    )

    response = await async_client.post(
        f"/api/v1/chats/{chat_id}/rewind",
        json={"message_id": ids["u2"]},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    data = body["data"]
    assert data["composer_text"] == "Second question"
    assert data["deleted_count"] == 2
    assert data["message_index"] == 2


@pytest.mark.asyncio
async def test_rewind_rejects_assistant_message(async_client: httpx.AsyncClient) -> None:
    chat_id = f"rewind-assist-{uuid.uuid4().hex[:8]}"
    await _create_chat(chat_id)
    ids = await _insert_messages(chat_id)

    response = await async_client.post(
        f"/api/v1/chats/{chat_id}/rewind",
        json={"message_id": ids["a2"]},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_truncate_after_calls_checkpoint_sync(
    async_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chat_id = f"rewind-trunc-{uuid.uuid4().hex[:8]}"
    await _create_chat(chat_id)
    ids = await _insert_messages(chat_id)
    synced: list[str] = []

    async def _fake_sync(target_chat_id: str) -> int:
        synced.append(target_chat_id)
        return 2

    monkeypatch.setattr(
        "app.services.chat.session_continuity_service.sync_chat_checkpoint_from_db",
        _fake_sync,
    )

    response = await async_client.post(
        f"/api/v1/chats/{chat_id}/truncate-after",
        json={"message_id": ids["u2"]},
    )
    assert response.status_code == 200
    assert synced == [chat_id]


@pytest.mark.asyncio
async def test_truncate_after_propagates_checkpoint_sync_error(
    async_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chat_id = f"rewind-sync-fail-{uuid.uuid4().hex[:8]}"
    await _create_chat(chat_id)
    ids = await _insert_messages(chat_id)

    async def _raise_sync(_chat_id: str) -> int:
        raise ContinuitySyncError("Synced 0/2 checkpoint threads for chat test-chat")

    monkeypatch.setattr(
        "app.services.chat.chat_turn._ChatTurnMixin._sync_checkpoint_after_mutation",
        _raise_sync,
    )

    response = await async_client.post(
        f"/api/v1/chats/{chat_id}/truncate-after",
        json={"message_id": ids["u2"]},
    )
    assert response.status_code == 500


@pytest.mark.asyncio
async def test_rewind_does_not_pause_goal_when_message_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.chat.chat_service import ChatService

    chat_id = f"rewind-no-pause-{uuid.uuid4().hex[:8]}"
    await _create_chat(chat_id)

    pause_calls: list[str] = []

    async def _fake_pause(target_chat_id: str) -> bool:
        pause_calls.append(target_chat_id)
        return True

    monkeypatch.setattr(
        "app.services.chat.session_continuity_service.pause_active_goal_for_rewind",
        _fake_pause,
    )

    result = await ChatService.rewind_to_message(chat_id, str(uuid.uuid4()))
    assert result.success is False
    assert result.error == "MESSAGE_NOT_FOUND"
    assert pause_calls == []


@pytest.mark.asyncio
async def test_rewind_both_scope_reverts_files(
    async_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """scope=both reverts deleted message files and returns the revert summary."""
    chat_id = f"rewind-both-{uuid.uuid4().hex[:8]}"
    await _create_chat(chat_id)
    ids = await _insert_messages(chat_id)

    async def _fake_sync(_chat_id: str) -> int:
        return 2

    monkeypatch.setattr(
        "app.services.chat.session_continuity_service.sync_chat_checkpoint_from_db",
        _fake_sync,
    )

    async def _fake_pause(_chat_id: str) -> bool:
        return True

    monkeypatch.setattr(
        "app.services.chat.session_continuity_service.pause_active_goal_for_rewind",
        _fake_pause,
    )

    revert_calls: list[tuple[str, list[str]]] = []

    async def _fake_revert_files(chat_id_arg: str, deleted_ids: list[str]) -> dict[str, list[str]]:
        revert_calls.append((chat_id_arg, deleted_ids))
        return {
            "reverted_files": ["a.py", "b.py"],
            "warnings": ["skipped c.py"],
            "skipped_files": ["c.py"],
        }

    monkeypatch.setattr(
        "app.services.chat.chat_turn._ChatTurnMixin._revert_files_for_messages",
        _fake_revert_files,
    )

    response = await async_client.post(
        f"/api/v1/chats/{chat_id}/rewind",
        json={"message_id": ids["u2"], "scope": "both"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["reverted_files"] == ["a.py", "b.py"]
    assert data["file_warnings"] == ["skipped c.py"]
    assert data["skipped_files"] == ["c.py"]

    assert len(revert_calls) == 1
    assert revert_calls[0][0] == chat_id
    assert set(revert_calls[0][1]) == {ids["u2"], ids["a2"]}


@pytest.mark.asyncio
async def test_rewind_conversation_scope_skips_file_revert(
    async_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Default conversation scope does not touch files."""
    chat_id = f"rewind-conv-{uuid.uuid4().hex[:8]}"
    await _create_chat(chat_id)
    ids = await _insert_messages(chat_id)

    async def _fake_sync(_chat_id: str) -> int:
        return 2

    monkeypatch.setattr(
        "app.services.chat.session_continuity_service.sync_chat_checkpoint_from_db",
        _fake_sync,
    )

    async def _fake_pause(_chat_id: str) -> bool:
        return False

    monkeypatch.setattr(
        "app.services.chat.session_continuity_service.pause_active_goal_for_rewind",
        _fake_pause,
    )

    revert_calls: list[tuple[str, list[str]]] = []

    async def _fake_revert_files(chat_id_arg: str, deleted_ids: list[str]) -> dict[str, list[str]]:
        revert_calls.append((chat_id_arg, deleted_ids))
        return {"reverted_files": [], "warnings": [], "skipped_files": []}

    monkeypatch.setattr(
        "app.services.chat.chat_turn._ChatTurnMixin._revert_files_for_messages",
        _fake_revert_files,
    )

    response = await async_client.post(
        f"/api/v1/chats/{chat_id}/rewind",
        json={"message_id": ids["u2"]},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["reverted_files"] == []
    assert revert_calls == []


@pytest.mark.asyncio
async def test_revert_files_for_messages_reverts_newest_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Files are reverted newest message first, with cleanup and agent notify."""
    from types import SimpleNamespace

    from myrm_agent_harness.agent.meta_tools.file_ops.revert_service import RevertService

    from app.services.chat.chat_turn import _ChatTurnMixin

    reverted_order: list[str] = []

    async def _fake_revert(session_id: str, message_id: str):
        reverted_order.append(message_id)
        return SimpleNamespace(
            reverted_files=[f"{message_id}_a.txt", f"{message_id}_b.txt"],
            warnings=[],
            skipped_files=[],
        )

    monkeypatch.setattr(
        "app.services.files.revert_hydrate.ensure_session_snapshots_hydrated",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "app.services.files.revert_hydrate.cleanup_persisted_snapshots",
        AsyncMock(),
    )
    monkeypatch.setattr(RevertService, "revert_message", _fake_revert)

    notify_calls: list[dict] = []
    monkeypatch.setattr(
        "app.services.files.revert_agent_notify.notify_agent_of_turn_revert",
        lambda **kwargs: notify_calls.append(kwargs),
    )

    result = await _ChatTurnMixin._revert_files_for_messages("chat-1", ["msg-1", "msg-2"])

    assert reverted_order == ["msg-2", "msg-1"]
    assert result["reverted_files"] == ["msg-2_a.txt", "msg-2_b.txt", "msg-1_a.txt", "msg-1_b.txt"]
    assert len(notify_calls) == 1
    assert notify_calls[0]["session_id"] == "chat-1"
    assert notify_calls[0]["reverted_files"] == result["reverted_files"]


@pytest.mark.asyncio
async def test_revert_files_for_messages_skips_messages_without_snapshots(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Messages without snapshots are skipped gracefully; no notify without reverts."""
    from types import SimpleNamespace

    from myrm_agent_harness.agent.meta_tools.file_ops.revert_service import RevertService

    from app.services.chat.chat_turn import _ChatTurnMixin

    async def _fake_revert(session_id: str, message_id: str):
        return SimpleNamespace(reverted_files=[], warnings=["No snapshots"], skipped_files=[])

    monkeypatch.setattr(
        "app.services.files.revert_hydrate.ensure_session_snapshots_hydrated",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "app.services.files.revert_hydrate.cleanup_persisted_snapshots",
        AsyncMock(),
    )
    monkeypatch.setattr(RevertService, "revert_message", _fake_revert)

    notify_calls: list[dict] = []
    monkeypatch.setattr(
        "app.services.files.revert_agent_notify.notify_agent_of_turn_revert",
        lambda **kwargs: notify_calls.append(kwargs),
    )

    result = await _ChatTurnMixin._revert_files_for_messages("chat-1", ["msg-1", "msg-2"])

    assert result["reverted_files"] == []
    assert result["warnings"] == ["No snapshots", "No snapshots"]
    assert notify_calls == []


@pytest.mark.asyncio
async def test_cleanup_orphan_snapshots_on_conversation_only_rewind(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Conversation-only rewind drops snapshot state for deleted messages."""
    from types import SimpleNamespace

    from app.services.chat.chat_turn import _ChatTurnMixin

    cleanup_calls: list[tuple[str, str]] = []

    async def _fake_cleanup(chat_id: str, message_id: str) -> None:
        cleanup_calls.append((chat_id, message_id))

    monkeypatch.setattr(
        "app.services.files.revert_hydrate.cleanup_persisted_snapshots",
        _fake_cleanup,
    )

    remove_calls: list[tuple[str, str]] = []
    fake_store = SimpleNamespace(
        remove_message=lambda session_id, message_id: remove_calls.append((session_id, message_id)),
    )
    monkeypatch.setattr(
        "myrm_agent_harness.agent.meta_tools.file_ops.observers.snapshot_observer.SnapshotStore",
        SimpleNamespace(get=lambda: fake_store),
    )

    await _ChatTurnMixin._cleanup_orphan_snapshots("chat-1", ["msg-1", "msg-2"])

    assert remove_calls == [("chat-1", "msg-1"), ("chat-1", "msg-2")]
    assert cleanup_calls == [("chat-1", "msg-1"), ("chat-1", "msg-2")]
