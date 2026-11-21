"""Integration tests: the artifact share seed route registers real artifacts a share link can read, and only answers in local mode."""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.database.models.artifact import Artifact
from app.services.hosting.artifact_files import resolve_artifact_deploy_files
from app.services.hosting.packager import PublishFile
from tests.support.minimal_app import build_minimal_app

app = build_minimal_app("chats", preset="chats")

_ROUTE = "/api/v1/chats/test/seed-artifact-share-fixture"


@pytest.fixture(autouse=True)
def _mock_upsert_processor_artifact() -> None:
    """Artifacts are registered for real here; the shared stand-in for the upsert is switched off."""


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


async def _seed_visible_agent(agent_id: str) -> None:
    from app.database.models.agent import Agent
    from app.platform_utils import get_session_factory

    async with get_session_factory()() as db:
        db.add(Agent(id=agent_id, name="Artifact Share Seed Agent", model_selection={"model": "gpt-4o-mini"}))
        await db.commit()


async def _stored_artifacts(chat_id: str) -> dict[str, Artifact]:
    from app.platform_utils import get_session_factory

    async with get_session_factory()() as db:
        rows = (await db.execute(select(Artifact).where(Artifact.chat_id == chat_id))).scalars().all()
    return {str(row.name): row for row in rows}


async def _files_a_share_link_reads(artifact_id: str) -> dict[str, PublishFile]:
    """The same lookup share creation runs: the chat's workspace root, not the process root, holds the vault object."""
    from app.platform_utils import get_session_factory
    from app.platform_utils.workspace_root import get_workspace_root

    async with get_session_factory()() as db:
        _artifact, files = await resolve_artifact_deploy_files(db, artifact_id, str(get_workspace_root()))
    return files


def _seed(client: TestClient) -> dict[str, str]:
    asyncio.run(_seed_visible_agent(f"agent_{uuid.uuid4().hex[:8]}"))
    with patch("app.api.chats.test_fixtures.artifact_share.is_local_mode", return_value=True):
        response = client.post(_ROUTE)
    assert response.status_code == 200, response.text
    body: dict[str, str] = response.json()
    return body


@pytest.mark.integration
class TestArtifactShareSeedFixture:
    def test_the_chart_page_and_the_report_are_registered_as_artifacts_of_a_new_chat(self, client: TestClient) -> None:
        body = _seed(client)

        chat_id = str(body["chat_id"])
        assert chat_id.startswith("e2eartshare")
        stored = asyncio.run(_stored_artifacts(chat_id))
        assert {name: str(row.id) for name, row in stored.items()} == {
            "chart.html": body["chart_artifact_id"],
            "report.md": body["report_artifact_id"],
        }
        assert all(row.source_path for row in stored.values())

    def test_each_artifact_is_found_alone_with_the_markup_the_browser_check_relies_on(self, client: TestClient) -> None:
        body = _seed(client)

        chart = asyncio.run(_files_a_share_link_reads(body["chart_artifact_id"]))
        report = asyncio.run(_files_a_share_link_reads(body["report_artifact_id"]))

        assert set(chart) == {"index.html"}
        assert set(report) == {"report.md"}
        assert "chart.js" in chart["index.html"].content and "animation: false" in chart["index.html"].content
        hostile = report["report.md"].content
        assert "<script>" in hostile and "onerror=" in hostile and "javascript:" in hostile

    def test_outside_local_mode_the_route_does_not_exist(self, client: TestClient) -> None:
        with patch("app.api.chats.test_fixtures.artifact_share.is_local_mode", return_value=False):
            response = client.post(_ROUTE)

        assert response.status_code == 404
