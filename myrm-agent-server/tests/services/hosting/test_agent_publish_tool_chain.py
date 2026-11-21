"""``artifact_publish`` through the real chain: executor path check, artifact registration, packaging, orchestrator.

Only the hosting platform itself is replaced, by a recorder of what each publication was handed.
"""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from langchain_core.tools import BaseTool
from myrm_agent_harness.toolkits.code_execution.config import ExecutionConfig
from myrm_agent_harness.toolkits.code_execution.executors.base import reset_executor, set_executor
from myrm_agent_harness.toolkits.code_execution.executors.local import LocalExecutor
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.artifact import Artifact, ArtifactVersion
from app.services.hosting.agent_publish_tool import create_artifact_publish_tool
from app.services.hosting.packager import PublishFile
from app.services.hosting.targets import list_hosting_targets
from app.services.hosting.types import HostingTarget, PublicationResult
from tests.support.chat_workspace import chats_bound_to_workspaces
from tests.support.hosting_api import CHAT_ID, seed_webhook_target

TARGET_ID = "tgt-1"
PAGE = '<link rel="stylesheet" href="style.css"><h1>Hello</h1>'
LOGGER = "app.services.hosting.agent_publish_tool"


@pytest.fixture(autouse=True)
def _mock_upsert_processor_artifact() -> None:
    """Artifacts are registered for real here; the shared stand-in for the upsert is switched off."""


@dataclass(frozen=True)
class Publication:
    """What the platform was handed by one publication."""

    artifact_id: str
    files: dict[str, str]
    existing_project_ref: str | None


@dataclass
class Platform:
    """The hosting platform: records what each publication was handed and answers with a stable address."""

    failure: str | None = None
    calls: list[Publication] = field(default_factory=list)

    async def publish(
        self,
        *,
        target: HostingTarget,
        credentials: dict[str, object],
        artifact_id: str,
        artifact_name: str,
        files: dict[str, PublishFile],
        existing_project_ref: str | None,
    ) -> PublicationResult:
        self.calls.append(Publication(artifact_id, {name: file.content for name, file in files.items()}, existing_project_ref))
        if self.failure:
            return PublicationResult(False, "", "", "", "ERROR", error=self.failure)
        return PublicationResult(
            True, f"https://pages.example/{artifact_id}", f"pub-{len(self.calls)}", f"project-{artifact_id}", "DEPLOYED"
        )


@dataclass
class Rig:
    tool: BaseTool
    platform: Platform
    workspace: Path
    db: AsyncSession

    async def publish(self, path: str, **arguments: str) -> dict[str, object]:
        result = await self.tool.ainvoke({"path": path, **arguments})
        assert isinstance(result, dict)
        return result

    async def count(self, model: type[Artifact] | type[ArtifactVersion]) -> int:
        return (await self.db.execute(select(func.count()).select_from(model))).scalar_one()


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    root = tmp_path / "workspace"
    root.mkdir()
    return root


@pytest.fixture
def executor(workspace: Path) -> Iterator[LocalExecutor]:
    local = LocalExecutor(config=ExecutionConfig(), workspace_path=str(workspace))
    token = set_executor(local)
    yield local
    reset_executor(token)


@pytest.fixture
def rig(db_session: AsyncSession, workspace: Path, executor: LocalExecutor, monkeypatch: pytest.MonkeyPatch) -> Iterator[Rig]:
    platform = Platform()

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        yield db_session

    monkeypatch.setattr("app.database.connection.get_session", session)
    monkeypatch.setattr("app.services.hosting.orchestrator.get_hosting_provider", lambda _provider_type: platform)
    with chats_bound_to_workspaces({CHAT_ID: workspace}):
        yield Rig(create_artifact_publish_tool(CHAT_ID), platform, workspace, db_session)


@pytest_asyncio.fixture
async def target(db_session: AsyncSession) -> str:
    await seed_webhook_target(db_session, TARGET_ID)
    return TARGET_ID


def _site(directory: Path, color: str = "red") -> Path:
    directory.mkdir(parents=True)
    (directory / "style.css").write_text(f"h1 {{ color: {color}; }}", encoding="utf-8")
    page = directory / "index.html"
    page.write_text(PAGE, encoding="utf-8")
    return page


def _metadata(result: dict[str, object]) -> dict[str, object]:
    metadata = result["metadata"]
    assert isinstance(metadata, dict)
    return metadata


@pytest.mark.asyncio
async def test_a_workspace_file_is_published_with_the_files_it_references(rig: Rig, target: str) -> None:
    _site(rig.workspace / "site")

    result = await rig.publish("site/index.html")

    assert result["content"] == f"Published successfully! Live URL: https://pages.example/{_metadata(result)['artifact_id']}"
    assert _metadata(result)["hosting_target_id"] == target
    assert rig.platform.calls[0].files == {"index.html": PAGE, "style.css": "h1 { color: red; }"}


@pytest.mark.asyncio
async def test_every_spelling_of_the_path_publishes_the_same_artifact(rig: Rig, target: str) -> None:
    page = _site(rig.workspace / "site")

    spellings = ["site/index.html", "./site/index.html", "site/../site/index.html", str(page)]
    published = [_metadata(await rig.publish(spelling))["artifact_id"] for spelling in spellings]

    assert len(set(published)) == 1
    assert await rig.count(Artifact) == 1


@pytest.mark.asyncio
async def test_publishing_a_file_again_after_an_edit_updates_the_same_page(rig: Rig, target: str) -> None:
    page = _site(rig.workspace / "site")
    first = await rig.publish("site/index.html")
    page.write_text("<h1>Edited</h1>", encoding="utf-8")

    second = await rig.publish("site/index.html")

    artifact_id = _metadata(first)["artifact_id"]
    assert _metadata(second)["artifact_id"] == artifact_id
    assert _metadata(second)["url"] == _metadata(first)["url"]
    assert rig.platform.calls[1].existing_project_ref == f"project-{artifact_id}"
    assert rig.platform.calls[1].files["index.html"] == "<h1>Edited</h1>"
    assert (await rig.count(Artifact), await rig.count(ArtifactVersion)) == (1, 2)


@pytest.mark.asyncio
async def test_two_pages_with_the_same_name_each_publish_their_own_files(rig: Rig, target: str) -> None:
    _site(rig.workspace / "site-a", "red")
    _site(rig.workspace / "site-b", "blue")

    await rig.publish("site-a/index.html")
    await rig.publish("site-b/index.html")

    styles = [call.files["style.css"] for call in rig.platform.calls]
    assert styles == ["h1 { color: red; }", "h1 { color: blue; }"]


@pytest.mark.asyncio
async def test_a_tenant_with_only_the_platform_token_publishes_without_opening_the_settings(
    rig: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.services.hosting.credentials.get_platform_vercel_token", lambda: "platform-token")
    _site(rig.workspace / "site")
    assert await list_hosting_targets(rig.db) == []

    result = await rig.publish("site/index.html")

    assert "error" not in _metadata(result)
    assert [target.provider_type for target in await list_hosting_targets(rig.db)] == ["vercel"]


@pytest.mark.asyncio
async def test_the_target_and_password_the_model_names_reach_the_orchestrator(rig: Rig, target: str) -> None:
    _site(rig.workspace / "site")
    outcome = PublicationResult(True, "https://secure.example.com", "pub", "project", "DEPLOYED")

    with patch("app.services.hosting.orchestrator.publish_artifact_to_target", new=AsyncMock(return_value=outcome)) as publish:
        result = await rig.publish("site/index.html", hosting_target_id="tgt-explicit", password="  SuperSecret2026  ")

    publish.assert_awaited_once()
    handed = publish.await_args
    assert handed is not None
    assert handed.args[1:] == (_metadata(result)["artifact_id"], str(rig.workspace.resolve()))
    assert handed.kwargs == {"hosting_target_id": "tgt-explicit", "password": "SuperSecret2026"}


@pytest.mark.parametrize("kind", ["relative", "absolute", "symlink"])
@pytest.mark.asyncio
async def test_a_file_outside_the_workspace_is_never_registered_or_published(
    rig: Rig, target: str, tmp_path: Path, caplog: pytest.LogCaptureFixture, kind: str
) -> None:
    outside = tmp_path / "outside" / "page.html"
    outside.parent.mkdir()
    outside.write_text("<h1>secret</h1>", encoding="utf-8")
    if kind == "symlink":
        if os.name == "nt":
            pytest.skip("creating symlinks needs elevated rights on Windows")
        (rig.workspace / "link.html").symlink_to(outside)
    path = {"relative": "../outside/page.html", "absolute": str(outside), "symlink": "link.html"}[kind]

    with caplog.at_level(logging.INFO, logger=LOGGER):
        result = await rig.publish(path)

    assert result == {"content": "Only files inside the workspace can be published.", "metadata": {"error": True, "path": path}}
    assert "artifact_publish: outcome=rejected reason=outside_workspace" in caplog.text
    assert (rig.platform.calls, await rig.count(Artifact)) == ([], 0)


@pytest.mark.asyncio
async def test_a_path_the_executor_grants_outside_the_workspace_is_still_refused(rig: Rig, target: str, tmp_path: Path) -> None:
    granted = tmp_path / "granted" / "page.html"
    granted.parent.mkdir()
    granted.write_text("<h1>granted</h1>", encoding="utf-8")
    # resolve_path lets a directory the user granted access to through; this tool only publishes workspace files.
    lenient = SimpleNamespace(
        workspace_path=str(rig.workspace),
        resolve_path=AsyncMock(side_effect=lambda path: str(Path(path).resolve())),
    )
    token = set_executor(lenient)  # type: ignore[arg-type]
    try:
        result = await rig.publish(str(granted))
    finally:
        reset_executor(token)

    assert result["content"] == "Only files inside the workspace can be published."
    assert (rig.platform.calls, await rig.count(Artifact)) == ([], 0)


@pytest.mark.parametrize(
    ("path", "message"),
    [
        ("", "path is required."),
        ("   ", "path is required."),
        ("site", "No file at that path in the workspace: site"),
        ("nope.html", "No file at that path in the workspace: nope.html"),
        (".DS_Store", "This file cannot be published: .DS_Store"),
    ],
)
@pytest.mark.asyncio
async def test_a_path_that_names_no_publishable_file_is_explained_to_the_model(
    rig: Rig, target: str, path: str, message: str
) -> None:
    _site(rig.workspace / "site")
    (rig.workspace / ".DS_Store").write_bytes(b"\x00")

    result = await rig.publish(path)

    assert result == {"content": message, "metadata": {"error": True, "path": path}}
    assert (rig.platform.calls, await rig.count(Artifact)) == ([], 0)


@pytest.mark.asyncio
async def test_without_a_hosting_target_nothing_is_registered(rig: Rig) -> None:
    _site(rig.workspace / "site")

    result = await rig.publish("site/index.html")

    assert result["content"] == "No hosting target configured. Please add a hosting target in Settings → Hosting first."
    assert (rig.platform.calls, await rig.count(Artifact)) == ([], 0)


@pytest.mark.asyncio
async def test_a_publication_the_platform_refuses_is_reported_with_its_reason(
    rig: Rig, target: str, caplog: pytest.LogCaptureFixture
) -> None:
    _site(rig.workspace / "site")
    rig.platform.failure = "quota exceeded"

    with caplog.at_level(logging.INFO, logger=LOGGER):
        result = await rig.publish("site/index.html")

    assert result["content"] == "Publication failed: quota exceeded"
    assert _metadata(result)["error"] is True
    assert (
        f"artifact_publish: outcome=failed artifact={_metadata(result)['artifact_id']} target={target} status=ERROR"
        in caplog.text
    )


@pytest.mark.asyncio
async def test_a_published_file_leaves_one_structured_line(rig: Rig, target: str, caplog: pytest.LogCaptureFixture) -> None:
    _site(rig.workspace / "site")

    with caplog.at_level(logging.INFO, logger=LOGGER):
        result = await rig.publish("site/index.html")

    assert f"artifact_publish: outcome=published artifact={_metadata(result)['artifact_id']} target={target}" in caplog.text


@pytest.mark.asyncio
async def test_a_session_without_a_workspace_publishes_nothing(rig: Rig, target: str) -> None:
    token = set_executor(None)
    try:
        result = await rig.publish("site/index.html")
    finally:
        reset_executor(token)

    assert result["content"] == "No workspace is available in this session."
