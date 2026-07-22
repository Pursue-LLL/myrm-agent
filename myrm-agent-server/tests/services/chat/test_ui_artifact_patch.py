"""Tests for cross-turn UI artifact data persistence."""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.dto import MessageDTO
from app.database.models import Chat
from app.database.repositories.chat_repo import ChatRepository
from app.services.agent.stream_session.stream_finalize import (
    finalize_agent_stream_session,
)
from app.services.agent.stream_session.stream_loop import ApprovalTimeoutHolder, ClarificationTimeoutHolder
from app.services.agent.streaming_support.stream_collector import StreamContentCollector
from app.services.chat.chat_service import ChatService
from app.services.chat.ui_artifact_patch import (
    merge_ui_artifact_data_in_extra_data,
    patch_ui_artifact_data_by_surface_id,
    patch_ui_artifact_data_updates,
)


def _make_chat(chat_id: str) -> Chat:
    return Chat(id=chat_id, title="UI Patch Chat", source="web")


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
async def cross_turn_ui_chat(db_session: AsyncSession) -> str:
    """Turn1 assistant hosts UI; turn2 assistant has no uiArtifacts."""
    chat_id = "ui-patch-cross-turn"
    db_session.add(_make_chat(chat_id))
    await db_session.flush()

    base = datetime(2025, 6, 1, 10, 0, 0)
    turn1_extra: dict[str, object] = {
        "uiArtifacts": [
            {
                "surface_id": "e2e_status_surface",
                "title": "Status",
                "components": [],
                "root_ids": [],
                "data": {"status": {"label": "E2E_UPDATE_INITIAL"}},
                "actions": [],
            },
        ],
    }
    msgs = [
        _make_msg(chat_id, "user", "Render status UI", msg_id="u1", created_at=base),
        _make_msg(
            chat_id,
            "assistant",
            "Rendered status UI",
            msg_id="a1",
            created_at=base + timedelta(seconds=1),
            extra_data=turn1_extra,
        ),
        _make_msg(
            chat_id,
            "user",
            "Update status",
            msg_id="u2",
            created_at=base + timedelta(seconds=2),
        ),
        _make_msg(
            chat_id,
            "assistant",
            "Updated status",
            msg_id="a2",
            created_at=base + timedelta(seconds=3),
        ),
    ]
    await ChatRepository.add_messages(db_session, msgs)
    await db_session.commit()
    return chat_id


class TestMergeUiArtifactDataInExtraData:
    def test_deep_merges_nested_fields(self) -> None:
        extra: dict[str, object] = {
            "uiArtifacts": [
                {
                    "surface_id": "s1",
                    "data": {"status": {"label": "INITIAL", "code": 1}},
                },
            ],
        }
        merged = merge_ui_artifact_data_in_extra_data(
            extra,
            "s1",
            {"status": {"label": "FINAL"}},
        )
        assert merged is True
        artifacts = extra["uiArtifacts"]
        assert isinstance(artifacts, list)
        artifact = artifacts[0]
        assert isinstance(artifact, dict)
        data = artifact["data"]
        assert isinstance(data, dict)
        status = data["status"]
        assert isinstance(status, dict)
        assert status["label"] == "FINAL"
        assert status["code"] == 1


class TestPatchUiArtifactDataBySurfaceId:
    async def test_patches_host_message_for_cross_turn_update(
        self, cross_turn_ui_chat: str
    ) -> None:
        patched = await patch_ui_artifact_data_by_surface_id(
            cross_turn_ui_chat,
            "e2e_status_surface",
            {"status": {"label": "E2E_UPDATE_FINAL"}},
        )
        assert patched is True

        messages = await ChatService.get_all_messages(cross_turn_ui_chat)
        turn1 = next(msg for msg in messages if msg.id == "a1")
        assert turn1.extra_data is not None
        artifacts = turn1.extra_data["uiArtifacts"]
        assert isinstance(artifacts, list)
        data = artifacts[0]["data"]
        assert isinstance(data, dict)
        status = data["status"]
        assert isinstance(status, dict)
        assert status["label"] == "E2E_UPDATE_FINAL"

    async def test_unknown_surface_returns_false(self, cross_turn_ui_chat: str) -> None:
        patched = await patch_ui_artifact_data_by_surface_id(
            cross_turn_ui_chat,
            "missing_surface",
            {"k": "v"},
        )
        assert patched is False


class TestPatchUiArtifactDataUpdates:
    async def test_merges_multiple_patches_for_same_surface(
        self, cross_turn_ui_chat: str
    ) -> None:
        await patch_ui_artifact_data_updates(
            cross_turn_ui_chat,
            [
                ("e2e_status_surface", {"status": {"code": 2}}),
                ("e2e_status_surface", {"status": {"label": "E2E_UPDATE_FINAL"}}),
            ],
        )

        messages = await ChatService.get_all_messages(cross_turn_ui_chat)
        turn1 = next(msg for msg in messages if msg.id == "a1")
        assert turn1.extra_data is not None
        status = turn1.extra_data["uiArtifacts"][0]["data"]["status"]
        assert isinstance(status, dict)
        assert status["label"] == "E2E_UPDATE_FINAL"
        assert status["code"] == 2


class TestStreamCollectorCrossTurnDataUpdate:
    def test_records_cross_turn_data_update_when_surface_not_in_current_turn(
        self,
    ) -> None:
        collector = StreamContentCollector(chat_id="chat_x", sibling_group_id="sib_x")
        collector.feed_event(
            {
                "type": "ui_update",
                "subtype": "data_update",
                "data": {
                    "surface_id": "e2e_status_surface",
                    "updates": {"status": {"label": "E2E_UPDATE_FINAL"}},
                },
                "messageId": "msg_turn2",
            }
        )

        assert collector.extra_data is None
        assert collector.cross_turn_data_updates == [
            ("e2e_status_surface", {"status": {"label": "E2E_UPDATE_FINAL"}}),
        ]

    def test_has_persistable_turn_when_only_ui_artifacts(self) -> None:
        collector = StreamContentCollector(
            chat_id="chat_ui_only", sibling_group_id="sib_ui"
        )
        assert collector.has_content is False
        assert collector.has_persistable_turn is False

        collector.feed_event(
            {
                "type": "ui_update",
                "subtype": "ui_artifact",
                "data": [
                    {
                        "surface_id": "e2e_status_surface",
                        "title": "Status",
                        "components": [],
                        "root_ids": [],
                        "data": {"status": "E2E_UPDATE_INITIAL"},
                        "actions": [],
                    },
                ],
                "messageId": "msg_turn1",
            }
        )

        assert collector.has_persistable_turn is True
        extra = collector.extra_data
        assert extra is not None
        artifacts = extra.get("uiArtifacts")
        assert isinstance(artifacts, list)
        assert artifacts[0]["data"]["status"] == "E2E_UPDATE_INITIAL"


class TestFinalizeCrossTurnUiPatch:
    @pytest.mark.asyncio
    async def test_finalize_applies_cross_turn_data_updates(self) -> None:
        session = MagicMock()
        session.request = MagicMock()
        session.request.chat_id = "chat_finalize_patch"
        session.request.timezone = "UTC"
        session.request.use_workflow = False
        session.cancel_token = MagicMock()
        session.cancel_token.is_cancelled = False
        session.params = MagicMock()
        session.params.message_id = "msg_finalize"
        session.params.model_cfg = MagicMock()
        session.params.locale = "en"
        session.extra_context = {}
        session.collector = MagicMock()
        session.collector.has_content = False
        session.collector.has_persistable_turn = False
        session.collector.content = ""
        session.collector.extra_data = None
        session.collector.cross_turn_data_updates = [
            ("surface_finalize", {"status": {"label": "FINAL"}}),
        ]
        session.monitor = AsyncMock()
        session.had_fatal_error = False

        with (
            patch(
                "app.services.agent.stream_session.stream_finalize.enqueue_context_compaction_telemetry",
            ),
            patch(
                "app.services.agent.stream_session.stream_finalize.clear_context_task_metrics",
            ),
            patch(
                "app.services.agent.stream_session.stream_finalize.CancellationRegistry"
            ),
            patch("app.services.agent.stream_session.stream_finalize.SteeringRegistry"),
            patch("app.services.agent.goal_registry.GoalRegistry"),
            patch("myrm_agent_harness.agent.security.user_credentials_ctx") as mock_ctx,
            patch(
                "myrm_agent_harness.agent.context_management.tracking.task_metrics.get_task_metrics",
                return_value=None,
            ),
            patch(
                "app.services.chat.ui_artifact_patch.patch_ui_artifact_data_updates",
                new_callable=AsyncMock,
            ) as mock_patch,
        ):
            mock_ctx.reset = MagicMock()
            await finalize_agent_stream_session(
                session, MagicMock(), ApprovalTimeoutHolder(), ClarificationTimeoutHolder()
            )

        mock_patch.assert_awaited_once_with(
            "chat_finalize_patch",
            [("surface_finalize", {"status": {"label": "FINAL"}})],
        )
