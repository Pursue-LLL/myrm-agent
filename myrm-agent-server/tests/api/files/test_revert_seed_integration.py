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
        assert reverted == 1
        assert file_path.read_text(encoding="utf-8") == "before\n"
        assert not snapshot_file.is_file()
