"""Integration: cross-turn update_ui_data persists to host message in SQLite."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.dto import MessageDTO
from app.database.models import Chat
from app.database.repositories.chat_repo import ChatRepository
from app.services.agent.streaming_support.stream_collector import StreamContentCollector
from app.services.chat.chat_service import ChatService
from app.services.chat.ui_artifact_patch import (
    patch_ui_artifact_data_by_surface_id,
    patch_ui_artifact_data_updates,
)


def _make_chat(chat_id: str) -> Chat:
    return Chat(id=chat_id, title="Cross-turn DB Integration", source="web")


def _make_msg(
    chat_id: str,
    role: str,
    content: str,
    *,
    msg_id: str,
    created_at: datetime,
    extra_data: dict[str, object] | None = None,
) -> MessageDTO:
    return MessageDTO(
        id=msg_id,
        chat_id=chat_id,
        role=role,
        content=content,
        sent_at=created_at,
        sent_timezone="UTC",
        created_at=created_at,
        extra_data=extra_data,
    )


@pytest.fixture
async def cross_turn_chat(db_session: AsyncSession) -> str:
    chat_id = "ui-cross-turn-db-integration"
    db_session.add(_make_chat(chat_id))
    await db_session.flush()

    base = datetime(2025, 7, 1, 12, 0, 0)
    turn1_extra: dict[str, object] = {
        "uiArtifacts": [
            {
                "surface_id": "integration_status_surface",
                "title": "Status",
                "components": [],
                "root_ids": [],
                "data": {"status": {"label": "E2E_UPDATE_INITIAL"}},
                "actions": [],
            },
        ],
    }
    await ChatRepository.add_messages(
        db_session,
        [
            _make_msg(chat_id, "user", "Render", msg_id="u1", created_at=base),
            _make_msg(
                chat_id,
                "assistant",
                "Rendered",
                msg_id="a1",
                created_at=base + timedelta(seconds=1),
                extra_data=turn1_extra,
            ),
        ],
    )
    await db_session.commit()
    return chat_id


@pytest.mark.integration
@pytest.mark.asyncio
async def test_stream_collector_cross_turn_queue_persists_to_host_message(
    cross_turn_chat: str,
) -> None:
    """Real collector queue + real SQLite patch; no mocks on persistence path."""
    collector = StreamContentCollector(
        chat_id=cross_turn_chat,
        sibling_group_id="sib_integration",
    )
    collector.feed_event(
        {
            "type": "ui_update",
            "subtype": "data_update",
            "data": {
                "surface_id": "integration_status_surface",
                "updates": {"status": {"label": "E2E_UPDATE_FINAL"}},
            },
            "messageId": "msg_turn2",
        }
    )

    assert collector.cross_turn_data_updates == [
        (
            "integration_status_surface",
            {"status": {"label": "E2E_UPDATE_FINAL"}},
        ),
    ]

    patched = await patch_ui_artifact_data_by_surface_id(
        cross_turn_chat,
        "integration_status_surface",
        {"status": {"label": "E2E_UPDATE_FINAL"}},
    )
    assert patched is True

    await patch_ui_artifact_data_updates(
        cross_turn_chat, collector.cross_turn_data_updates
    )

    messages = await ChatService.get_all_messages(cross_turn_chat)
    turn1 = next(msg for msg in messages if msg.id == "a1")
    assert turn1.extra_data is not None
    artifacts = turn1.extra_data["uiArtifacts"]
    assert isinstance(artifacts, list)
    data = artifacts[0]["data"]
    assert isinstance(data, dict)
    status = data["status"]
    assert isinstance(status, dict)
    assert status["label"] == "E2E_UPDATE_FINAL"
