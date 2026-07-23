"""Integration tests: revert seed variants + HTTP revert API (no RevertService mocks)."""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from myrm_agent_harness.agent.meta_tools.file_ops.observers.snapshot_observer import SnapshotStore

from tests.support.minimal_app import build_minimal_app

app = build_minimal_app("files", preset="chats")


@pytest.fixture
def client(init_test_database) -> TestClient:
    return TestClient(app)


async def _seed_visible_agent(agent_id: str, *, display_name: str) -> None:
    from app.database.models.agent import Agent
    from app.platform_utils import get_session_factory

    session_factory = get_session_factory()
    async with session_factory() as db:
        db.add(
            Agent(
                id=agent_id,
                name=display_name,
                model_selection={"model": "gpt-4o-mini"},
            ),
        )
        await db.commit()


def _seed(client: TestClient, *, variant: str = "modify") -> dict[str, object]:
    with patch("app.api.chats.test_fixtures.is_local_mode", return_value=True):
        resp = client.post(f"/api/v1/chats/test/seed-revert-fixture?variant={variant}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert str(body["chat_id"]).startswith("e2erevert")
    SnapshotStore.reset()
    return body


class TestRevertSeedIntegration:
    def test_revert_fixture_full_http_chain_modify(self, client: TestClient) -> None:
        agent_id = f"agent_{uuid.uuid4().hex[:8]}"
        asyncio.run(_seed_visible_agent(agent_id, display_name="Revert Seed Integration Agent"))

        seed_body = _seed(client, variant="modify")
        chat_id = str(seed_body["chat_id"])
        message_id = str(seed_body["message_id"])
        file_path = Path(str(seed_body["file_path"]))
        assert file_path.read_text(encoding="utf-8") == "revert fixture after\n"

        changes_resp = client.get(f"/api/v1/files/revert/changes/{chat_id}/{message_id}")
        assert changes_resp.status_code == 200
        changes = changes_resp.json()
        assert len(changes) == 1
        assert changes[0]["operation"] == "modify"

        diff_resp = client.get(f"/api/v1/files/revert/diff/{chat_id}/{message_id}")
        assert diff_resp.status_code == 200
        diffs = diff_resp.json()
        assert diffs[0]["original"] == "revert fixture before\n"
        assert diffs[0]["current"] == "revert fixture after\n"

        revert_resp = client.post(
            "/api/v1/files/revert/message",
            json={"session_id": chat_id, "message_id": message_id},
        )
        assert revert_resp.status_code == 200
        revert_body = revert_resp.json()
        assert revert_body["success"] is True
        assert str(file_path) in revert_body["reverted_files"]
        assert file_path.read_text(encoding="utf-8") == "revert fixture before\n"

        empty_resp = client.get(f"/api/v1/files/revert/changes/{chat_id}/{message_id}")
        assert empty_resp.status_code == 200
        assert empty_resp.json() == []

    def test_revert_message_notifies_agent_restore_inbox(self, client: TestClient) -> None:
        agent_id = f"agent_{uuid.uuid4().hex[:8]}"
        asyncio.run(_seed_visible_agent(agent_id, display_name="Revert Notify Agent"))

        seed_body = _seed(client, variant="modify")
        chat_id = str(seed_body["chat_id"])
        message_id = str(seed_body["message_id"])
        file_path = Path(str(seed_body["file_path"]))

        with patch("app.services.files.revert_agent_notify.notify_agent_of_turn_revert") as mock_notify:
            revert_resp = client.post(
                "/api/v1/files/revert/message",
                json={"session_id": chat_id, "message_id": message_id},
            )

        assert revert_resp.status_code == 200
        mock_notify.assert_called_once_with(
            session_id=chat_id,
            message_id=message_id,
            reverted_files=[str(file_path)],
        )

    def test_revert_session_notifies_agent_restore_inbox(self, client: TestClient) -> None:
        agent_id = f"agent_{uuid.uuid4().hex[:8]}"
        asyncio.run(_seed_visible_agent(agent_id, display_name="Revert Session Notify Agent"))

        seed_body = _seed(client, variant="session")
        chat_id = str(seed_body["chat_id"])
        file_path = Path(str(seed_body["file_path"]))
        file_path_b = Path(str(seed_body["file_path_b"]))

        with patch("app.services.files.revert_agent_notify.notify_agent_of_turn_revert") as mock_notify:
            revert_resp = client.post(
                "/api/v1/files/revert/session",
                json={"session_id": chat_id},
            )

        assert revert_resp.status_code == 200
        mock_notify.assert_called_once()
        kwargs = mock_notify.call_args.kwargs
        assert kwargs["session_id"] == chat_id
        assert kwargs["message_id"] is None
        assert set(kwargs["reverted_files"]) == {str(file_path), str(file_path_b)}

    def test_revert_create_deletes_new_file(self, client: TestClient) -> None:
        agent_id = f"agent_{uuid.uuid4().hex[:8]}"
        asyncio.run(_seed_visible_agent(agent_id, display_name="Revert Create Agent"))

        seed_body = _seed(client, variant="create")
        chat_id = str(seed_body["chat_id"])
        message_id = str(seed_body["message_id"])
        file_path = Path(str(seed_body["file_path"]))
        assert file_path.is_file()

        revert_resp = client.post(
            "/api/v1/files/revert/message",
            json={"session_id": chat_id, "message_id": message_id},
        )
        assert revert_resp.status_code == 200
        body = revert_resp.json()
        assert body["success"] is True
        assert not file_path.exists()

    def test_revert_empty_message_returns_no_changes(self, client: TestClient) -> None:
        agent_id = f"agent_{uuid.uuid4().hex[:8]}"
        asyncio.run(_seed_visible_agent(agent_id, display_name="Revert Empty Agent"))

        seed_body = _seed(client, variant="empty")
        chat_id = str(seed_body["chat_id"])
        message_id = str(seed_body["message_id"])

        changes_resp = client.get(f"/api/v1/files/revert/changes/{chat_id}/{message_id}")
        assert changes_resp.status_code == 200
        assert changes_resp.json() == []

        revert_resp = client.post(
            "/api/v1/files/revert/message",
            json={"session_id": chat_id, "message_id": message_id},
        )
        assert revert_resp.status_code == 200
        assert revert_resp.json()["success"] is False

    def test_revert_session_reverts_all_messages(self, client: TestClient) -> None:
        agent_id = f"agent_{uuid.uuid4().hex[:8]}"
        asyncio.run(_seed_visible_agent(agent_id, display_name="Revert Session Agent"))

        seed_body = _seed(client, variant="session")
        chat_id = str(seed_body["chat_id"])
        file_path = Path(str(seed_body["file_path"]))
        file_path_b = Path(str(seed_body["file_path_b"]))

        session_changes = client.get(f"/api/v1/files/revert/changes/{chat_id}")
        assert session_changes.status_code == 200
        grouped = session_changes.json()
        assert len(grouped) == 2

        revert_resp = client.post(
            "/api/v1/files/revert/session",
            json={"session_id": chat_id},
        )
        assert revert_resp.status_code == 200
        body = revert_resp.json()
        assert body["success"] is True
        assert len(body["reverted_files"]) == 2
        assert file_path.read_text(encoding="utf-8") == "revert fixture before\n"
        assert file_path_b.read_text(encoding="utf-8") == "file b before\n"

        assert client.get(f"/api/v1/files/revert/changes/{chat_id}").json() == {}

    def test_hydrate_finds_snapshots_at_harness_workspace_root(
        self, client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """SnapshotObserver persists via resolve_workspace_root(), not chat sandbox alone."""
        from myrm_agent_harness.agent.meta_tools.file_ops.observers.snapshot_observer import (
            FileSnapshot,
            SnapshotOp,
        )
        from myrm_agent_harness.toolkits.code_execution.utils.workspace_path import WorkspacePathResolver

        from app.database.dto import ChatCreate
        from app.services.chat.chat_service import ChatService

        monkeypatch.delenv("WORKSPACE_ROOT", raising=False)
        persist_root = tmp_path.resolve()
        WorkspacePathResolver._cached_workspace_root = persist_root

        sandbox_dir = tmp_path / "chat_sandbox"
        sandbox_dir.mkdir()

        chat_id = f"e2erevert{uuid.uuid4().hex[:8]}"
        message_id = str(uuid.uuid4())
        agent_id = f"agent_{uuid.uuid4().hex[:8]}"
        asyncio.run(_seed_visible_agent(agent_id, display_name="Hydrate Root Agent"))

        async def _setup_chat() -> None:
            await ChatService.create_or_update_chat(
                ChatCreate(
                    chat_id=chat_id,
                    title="Hydrate root test",
                    agent_id=agent_id,
                    messages=[],
                ),
            )
            await ChatService.update_chat_fields(chat_id, {"workspace_dir": str(sandbox_dir)})

        asyncio.run(_setup_chat())

        file_path = sandbox_dir / "revert_e2e_fixture.txt"
        file_path.write_text("after\n", encoding="utf-8")

        SnapshotStore.reset()
        store = SnapshotStore.get()
        store.record(
            chat_id,
            message_id,
            FileSnapshot(
                path=str(file_path),
                operation=SnapshotOp.MODIFY,
                original_content="before\n",
            ),
        )
        asyncio.run(store.persist_to_disk(str(persist_root), chat_id, message_id))

        snapshot_file = persist_root / ".myrm" / "snapshots" / chat_id / f"{message_id}.json"
        assert snapshot_file.is_file()

        SnapshotStore.reset()

        changes_resp = client.get(f"/api/v1/files/revert/changes/{chat_id}/{message_id}")
        assert changes_resp.status_code == 200
        changes = changes_resp.json()
        assert len(changes) == 1
        assert changes[0]["operation"] == "modify"
        assert changes[0]["path"] == str(file_path)
        assert changes[0]["revertible"] is True
        assert changes[0]["skip_reason"] is None

    def test_changes_api_surfaces_non_revertible_skipped_snapshot(
        self, client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from myrm_agent_harness.agent.meta_tools.file_ops.observers.snapshot_observer import (
            SnapshotOp,
            SnapshotSkipReason,
        )
        from myrm_agent_harness.toolkits.code_execution.utils.workspace_path import WorkspacePathResolver

        monkeypatch.delenv("WORKSPACE_ROOT", raising=False)
        persist_root = tmp_path.resolve()
        WorkspacePathResolver._cached_workspace_root = persist_root

        chat_id = f"e2erevert{uuid.uuid4().hex[:8]}"
        message_id = str(uuid.uuid4())
        file_path = persist_root / "large.bin"
        file_path.write_text("modified\n", encoding="utf-8")

        SnapshotStore.reset()
        store = SnapshotStore.get()
        store.record_skipped(
            chat_id,
            message_id,
            str(file_path),
            SnapshotOp.MODIFY,
            SnapshotSkipReason.FILE_TOO_LARGE,
        )
        asyncio.run(store.persist_to_disk(str(persist_root), chat_id, message_id))

        SnapshotStore.reset()

        changes_resp = client.get(f"/api/v1/files/revert/changes/{chat_id}/{message_id}")
        assert changes_resp.status_code == 200
        changes = changes_resp.json()
        assert len(changes) == 1
        assert changes[0]["revertible"] is False
        assert changes[0]["skip_reason"] == "file_too_large"

        revert_resp = client.post(
            "/api/v1/files/revert/message",
            json={"session_id": chat_id, "message_id": message_id},
        )
        assert revert_resp.status_code == 200
        assert revert_resp.json()["success"] is False
        assert file_path.read_text(encoding="utf-8") == "modified\n"

    def test_revert_large_skip_fixture_surfaces_non_revertible(self, client: TestClient) -> None:
        agent_id = f"agent_{uuid.uuid4().hex[:8]}"
        asyncio.run(_seed_visible_agent(agent_id, display_name="Revert Large Skip Agent"))

        seed_body = _seed(client, variant="large_skip")
        chat_id = str(seed_body["chat_id"])
        message_id = str(seed_body["message_id"])

        changes_resp = client.get(f"/api/v1/files/revert/changes/{chat_id}/{message_id}")
        assert changes_resp.status_code == 200
        changes = changes_resp.json()
        assert len(changes) == 1
        assert changes[0]["revertible"] is False
        assert changes[0]["skip_reason"] == "file_too_large"

    def test_channel_revert_cleans_disk_snapshot(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from myrm_agent_harness.agent.meta_tools.file_ops.observers.snapshot_observer import (
            FileSnapshot,
            SnapshotOp,
        )
        from myrm_agent_harness.toolkits.code_execution.utils.workspace_path import WorkspacePathResolver

        from app.core.channel_bridge.turn_handler import _revert_messages

        monkeypatch.delenv("WORKSPACE_ROOT", raising=False)
        persist_root = tmp_path.resolve()
        WorkspacePathResolver._cached_workspace_root = persist_root

        chat_id = f"e2erevert{uuid.uuid4().hex[:8]}"
        message_id = str(uuid.uuid4())
        file_path = persist_root / "notes.txt"
        file_path.write_text("after\n", encoding="utf-8")

        SnapshotStore.reset()
        store = SnapshotStore.get()
        store.record(
            chat_id,
            message_id,
            FileSnapshot(
                path=str(file_path),
                operation=SnapshotOp.MODIFY,
                original_content="before\n",
            ),
        )
        asyncio.run(store.persist_to_disk(str(persist_root), chat_id, message_id))
        snapshot_file = persist_root / ".myrm" / "snapshots" / chat_id / f"{message_id}.json"
        assert snapshot_file.is_file()

        reverted = asyncio.run(_revert_messages(chat_id, [message_id]))
        assert reverted.reverted_count == 1
        assert file_path.read_text(encoding="utf-8") == "before\n"
        assert not snapshot_file.is_file()


@pytest.fixture(autouse=True)
def _clear_restore_inbox() -> None:
    from myrm_agent_harness.agent.file_snapshot.restore_inbox import _pending

    _pending.clear()
    yield
    _pending.clear()


class TestRestoreInboxIntegration:
    def test_revert_message_http_pushes_real_restore_inbox(self, client: TestClient) -> None:
        from myrm_agent_harness.agent.file_snapshot.restore_inbox import drain_restore_notifications

        agent_id = f"agent_{uuid.uuid4().hex[:8]}"
        asyncio.run(_seed_visible_agent(agent_id, display_name="Restore Inbox HTTP Agent"))

        seed_body = _seed(client, variant="modify")
        chat_id = str(seed_body["chat_id"])
        message_id = str(seed_body["message_id"])
        file_path = Path(str(seed_body["file_path"]))

        revert_resp = client.post(
            "/api/v1/files/revert/message",
            json={"session_id": chat_id, "message_id": message_id},
        )
        assert revert_resp.status_code == 200
        assert revert_resp.json()["success"] is True

        notice = drain_restore_notifications()
        assert notice is not None
        assert "[System: File rollback detected]" in notice
        assert str(file_path) in notice
        assert "Re-read any files you previously modified" in notice
        assert drain_restore_notifications() is None

    def test_revert_empty_message_does_not_push_restore_inbox(self, client: TestClient) -> None:
        from myrm_agent_harness.agent.file_snapshot.restore_inbox import drain_restore_notifications

        agent_id = f"agent_{uuid.uuid4().hex[:8]}"
        asyncio.run(_seed_visible_agent(agent_id, display_name="Restore Inbox Empty Agent"))

        seed_body = _seed(client, variant="empty")
        chat_id = str(seed_body["chat_id"])
        message_id = str(seed_body["message_id"])

        revert_resp = client.post(
            "/api/v1/files/revert/message",
            json={"session_id": chat_id, "message_id": message_id},
        )
        assert revert_resp.status_code == 200
        assert revert_resp.json()["success"] is False
        assert drain_restore_notifications() is None

    def test_channel_revert_messages_pushes_real_restore_inbox(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from myrm_agent_harness.agent.file_snapshot.restore_inbox import drain_restore_notifications
        from myrm_agent_harness.agent.meta_tools.file_ops.observers.snapshot_observer import (
            FileSnapshot,
            SnapshotOp,
        )
        from myrm_agent_harness.toolkits.code_execution.utils.workspace_path import WorkspacePathResolver

        from app.core.channel_bridge.turn_handler import _revert_messages

        monkeypatch.delenv("WORKSPACE_ROOT", raising=False)
        persist_root = tmp_path.resolve()
        WorkspacePathResolver._cached_workspace_root = persist_root

        chat_id = f"e2erevert{uuid.uuid4().hex[:8]}"
        message_id = str(uuid.uuid4())
        file_path = persist_root / "notes.txt"
        file_path.write_text("after\n", encoding="utf-8")

        SnapshotStore.reset()
        store = SnapshotStore.get()
        store.record(
            chat_id,
            message_id,
            FileSnapshot(
                path=str(file_path),
                operation=SnapshotOp.MODIFY,
                original_content="before\n",
            ),
        )
        asyncio.run(store.persist_to_disk(str(persist_root), chat_id, message_id))

        outcome = asyncio.run(_revert_messages(chat_id, [message_id]))
        assert outcome.reverted_count == 1

        notice = drain_restore_notifications()
        assert notice is not None
        assert "[System: File rollback detected]" in notice
        assert str(file_path) in notice
        assert "Re-read any files you previously modified" in notice

    def test_revert_session_http_pushes_real_restore_inbox(self, client: TestClient) -> None:
        from myrm_agent_harness.agent.file_snapshot.restore_inbox import drain_restore_notifications

        agent_id = f"agent_{uuid.uuid4().hex[:8]}"
        asyncio.run(_seed_visible_agent(agent_id, display_name="Restore Inbox Session Agent"))

        seed_body = _seed(client, variant="session")
        chat_id = str(seed_body["chat_id"])
        file_path = Path(str(seed_body["file_path"]))
        file_path_b = Path(str(seed_body["file_path_b"]))

        revert_resp = client.post(
            "/api/v1/files/revert/session",
            json={"session_id": chat_id},
        )
        assert revert_resp.status_code == 200
        assert revert_resp.json()["success"] is True

        notice = drain_restore_notifications()
        assert notice is not None
        assert "[System: File rollback detected]" in notice
        assert str(file_path) in notice
        assert str(file_path_b) in notice
        assert "2 file(s) restored" in notice

    def test_channel_revert_multi_message_dedupes_inbox_paths(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from myrm_agent_harness.agent.file_snapshot.restore_inbox import drain_restore_notifications
        from myrm_agent_harness.agent.meta_tools.file_ops.observers.snapshot_observer import (
            FileSnapshot,
            SnapshotOp,
        )
        from myrm_agent_harness.toolkits.code_execution.utils.workspace_path import WorkspacePathResolver

        from app.core.channel_bridge.turn_handler import _revert_messages

        monkeypatch.delenv("WORKSPACE_ROOT", raising=False)
        persist_root = tmp_path.resolve()
        WorkspacePathResolver._cached_workspace_root = persist_root

        chat_id = f"e2erevert{uuid.uuid4().hex[:8]}"
        message_a = str(uuid.uuid4())
        message_b = str(uuid.uuid4())
        shared_path = persist_root / "shared.txt"
        shared_path.write_text("v2\n", encoding="utf-8")

        SnapshotStore.reset()
        store = SnapshotStore.get()
        for mid, original in ((message_a, "v0\n"), (message_b, "v1\n")):
            store.record(
                chat_id,
                mid,
                FileSnapshot(
                    path=str(shared_path),
                    operation=SnapshotOp.MODIFY,
                    original_content=original,
                ),
            )
            asyncio.run(store.persist_to_disk(str(persist_root), chat_id, mid))

        outcome = asyncio.run(_revert_messages(chat_id, [message_a, message_b]))
        assert outcome.reverted_count == 2

        notice = drain_restore_notifications()
        assert notice is not None
        assert notice.count(str(shared_path)) == 1
