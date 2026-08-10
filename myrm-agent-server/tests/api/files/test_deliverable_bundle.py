"""Unit tests for §7 Office Full-Chain Delivery — deliverables collection & bundle download."""

from __future__ import annotations

import io
import zipfile
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.artifact import Artifact, ArtifactVersion
from app.services.agent.goals.goal_registry import ServerGoalManager

# ══════════════════════════════════════════════════════════════════════════════
# §1: _collect_session_deliverables
# ══════════════════════════════════════════════════════════════════════════════


class TestCollectSessionDeliverables:
    @pytest.mark.asyncio
    async def test_collects_artifacts_by_session(self, db_session: AsyncSession) -> None:
        """Goal completion should collect all non-deleted artifacts in the session."""
        session_id = "chat-delivery-001"

        a1 = Artifact(id="art-a", name="report.docx", chat_id=session_id)
        a2 = Artifact(id="art-b", name="slides.pptx", chat_id=session_id)
        a3 = Artifact(id="art-c", name="deleted.xlsx", chat_id=session_id, is_deleted=True)
        a4 = Artifact(id="art-d", name="other-session.docx", chat_id="chat-other")
        db_session.add_all([a1, a2, a3, a4])
        await db_session.commit()

        @asynccontextmanager
        async def _mock_get_session():
            yield db_session

        from app.services.agent.goals.goal_registry import _collect_session_deliverables

        with patch("app.database.connection.get_session", _mock_get_session):
            result = await _collect_session_deliverables(session_id)

        assert len(result) == 2
        filenames = {d["filename"] for d in result}
        assert filenames == {"report.docx", "slides.pptx"}
        assert all("id" in d for d in result)

    @pytest.mark.asyncio
    async def test_returns_empty_for_no_artifacts(self, db_session: AsyncSession) -> None:
        @asynccontextmanager
        async def _mock_get_session():
            yield db_session

        from app.services.agent.goals.goal_registry import _collect_session_deliverables

        with patch("app.database.connection.get_session", _mock_get_session):
            result = await _collect_session_deliverables("nonexistent-session")

        assert result == []

    @pytest.mark.asyncio
    async def test_consolidation_writes_metadata(self, db_session: AsyncSession) -> None:
        """ServerGoalManager should write deliverables into goal.metadata on completion."""
        session_id = "chat-meta-001"
        a1 = Artifact(id="art-m1", name="budget.xlsx", chat_id=session_id)
        a2 = Artifact(id="art-m2", name="summary.pdf", chat_id=session_id)
        db_session.add_all([a1, a2])
        await db_session.commit()

        @asynccontextmanager
        async def _mock_get_session():
            yield db_session

        manager = ServerGoalManager(AsyncMock(), session_id=session_id)
        manager._storage = AsyncMock()
        goal = SimpleNamespace(goal_id="g-1", metadata={})

        with patch("app.database.connection.get_session", _mock_get_session):
            await manager._consolidate_decisions_on_completion(goal)

        assert "deliverables" in goal.metadata
        assert len(goal.metadata["deliverables"]) == 2
        manager._storage.save_goal.assert_awaited_once_with(goal)

    @pytest.mark.asyncio
    async def test_consolidation_noop_without_session(self) -> None:
        manager = ServerGoalManager(AsyncMock(), session_id=None)
        goal = SimpleNamespace(goal_id="g-2", metadata={})
        await manager._consolidate_decisions_on_completion(goal)
        assert "deliverables" not in goal.metadata


# ══════════════════════════════════════════════════════════════════════════════
# §2: download-bundle endpoint
# ══════════════════════════════════════════════════════════════════════════════


class TestDownloadBundle:
    @pytest.mark.asyncio
    async def test_bundles_multiple_artifacts(
        self, client: TestClient, db_session: AsyncSession, tmp_path
    ) -> None:
        vault_dir = tmp_path / ".agent" / "vault" / "objects"
        vault_dir.mkdir(parents=True, exist_ok=True)

        now = datetime.now(timezone.utc)

        a1 = Artifact(id="bundle-a1", name="report.docx", chat_id="chat-b1")
        a2 = Artifact(id="bundle-a2", name="slides.pptx", chat_id="chat-b1")
        db_session.add_all([a1, a2])
        await db_session.flush()

        content1 = b"doc-content-1"
        content2 = b"ppt-content-2"
        (vault_dir / "obj-1").write_bytes(content1)
        (vault_dir / "obj-2").write_bytes(content2)

        v1 = ArtifactVersion(
            id="v-b1", artifact_id="bundle-a1",
            vault_uri="vault://obj-1", sha256_hash="fake",
            created_at=now,
        )
        v2 = ArtifactVersion(
            id="v-b2", artifact_id="bundle-a2",
            vault_uri="vault://obj-2", sha256_hash="fake",
            created_at=now,
        )
        db_session.add_all([v1, v2])
        await db_session.commit()

        from myrm_agent_harness.agent.artifacts.vault import ArtifactVault

        def mock_get_path(obj_id: str):
            return vault_dir / obj_id

        with (
            patch("app.api.dependencies.get_workspace_root", return_value=tmp_path),
            patch.object(ArtifactVault, "get_object_path", side_effect=mock_get_path),
        ):
            response = client.post(
                "/api/v1/files/artifacts/download-bundle",
                json={"artifact_ids": ["bundle-a1", "bundle-a2"], "chat_id": "chat-b1"},
            )
            assert response.status_code == 200
            assert response.headers["content-type"] == "application/zip"

            zf = zipfile.ZipFile(io.BytesIO(response.content))
            names = zf.namelist()
            assert "report.docx" in names
            assert "slides.pptx" in names
            assert zf.read("report.docx") == content1
            assert zf.read("slides.pptx") == content2

    @pytest.mark.asyncio
    async def test_deduplicates_filenames(
        self, client: TestClient, db_session: AsyncSession, tmp_path
    ) -> None:
        vault_dir = tmp_path / ".agent" / "vault" / "objects"
        vault_dir.mkdir(parents=True, exist_ok=True)

        now = datetime.now(timezone.utc)

        a1 = Artifact(id="dup-a1", name="report.docx", chat_id="chat-dup")
        a2 = Artifact(id="dup-a2", name="report.docx", chat_id="chat-dup")
        db_session.add_all([a1, a2])
        await db_session.flush()

        (vault_dir / "obj-dup1").write_bytes(b"v1")
        (vault_dir / "obj-dup2").write_bytes(b"v2")

        v1 = ArtifactVersion(
            id="v-dup1", artifact_id="dup-a1",
            vault_uri="vault://obj-dup1", sha256_hash="x",
            created_at=now,
        )
        v2 = ArtifactVersion(
            id="v-dup2", artifact_id="dup-a2",
            vault_uri="vault://obj-dup2", sha256_hash="y",
            created_at=now,
        )
        db_session.add_all([v1, v2])
        await db_session.commit()

        from myrm_agent_harness.agent.artifacts.vault import ArtifactVault

        def mock_get_path(obj_id: str):
            return vault_dir / obj_id

        with (
            patch("app.api.dependencies.get_workspace_root", return_value=tmp_path),
            patch.object(ArtifactVault, "get_object_path", side_effect=mock_get_path),
        ):
            response = client.post(
                "/api/v1/files/artifacts/download-bundle",
                json={"artifact_ids": ["dup-a1", "dup-a2"], "chat_id": "chat-dup"},
            )
            assert response.status_code == 200
            zf = zipfile.ZipFile(io.BytesIO(response.content))
            names = zf.namelist()
            assert len(names) == 2
            assert "report.docx" in names
            deduped = [n for n in names if n != "report.docx"]
            assert len(deduped) == 1
            # Deduplication appends _{id[:6]} to stem: report_dup-a1.docx or report_dup-a2.docx
            assert deduped[0].startswith("report_") and deduped[0].endswith(".docx")

    @pytest.mark.asyncio
    async def test_empty_ids_returns_400(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/files/artifacts/download-bundle",
            json={"artifact_ids": [], "chat_id": "chat-x"},
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_nonexistent_ids_returns_404(
        self, client: TestClient, db_session: AsyncSession
    ) -> None:
        response = client.post(
            "/api/v1/files/artifacts/download-bundle",
            json={"artifact_ids": ["non-exist-1", "non-exist-2"], "chat_id": "chat-y"},
        )
        assert response.status_code == 404
