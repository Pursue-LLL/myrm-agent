"""POST /wiki/compile queues the sources and wakes the background worker; it never waits for the compile."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from myrm_agent_harness.toolkits.wiki.core.config import WikiConfig
from myrm_agent_harness.toolkits.wiki.core.structure import WikiStructure
from myrm_agent_harness.toolkits.wiki.pipeline.compiler import WikiCompiler
from myrm_agent_harness.toolkits.wiki.pipeline.resilience import CompileRunSnapshot

from app.api.wiki.router import _get_wiki_archiver
from app.core.security.auth.identity import LOCAL_USER_ID

_PUBLISH = "app.services.wiki.ingest_events.publish_wiki_ingest_snapshot"
_SCHEDULE_ASSETS = "app.services.wiki.asset_index_service.schedule_wiki_asset_index"
_DEDUP_BLOCKS = "app.services.wiki.dedup_runner.wiki_dedup_blocks_compile"


@dataclass(frozen=True, slots=True)
class _FakeIdentity:
    user_id: str = LOCAL_USER_ID
    auth_source: str = "loopback"
    loopback: bool = True
    client_ip: str = "127.0.0.1"
    private_net: bool = False


@pytest.fixture(autouse=True)
def _bypass_auth() -> Iterator[None]:
    with patch("app.middleware.auth.resolve_identity", return_value=_FakeIdentity()):
        yield


def _client_for(archiver: object) -> TestClient:
    from tests.support.minimal_app import build_minimal_app

    app = build_minimal_app(preset="wiki")

    async def _override() -> object:
        return archiver

    app.dependency_overrides[_get_wiki_archiver] = _override
    return TestClient(app)


def _archiver(*, pending: int = 0, processing: int = 0, run: CompileRunSnapshot | None = None) -> MagicMock:
    archiver = MagicMock()
    archiver._compiler.enqueue_changed_sources = AsyncMock(return_value=pending)
    archiver._compiler.compile_all = AsyncMock()
    archiver._queue.get_stats.return_value = {"pending": pending, "processing": processing, "completed": 0, "failed": 0}
    archiver._queue.get_compile_run.return_value = run or CompileRunSnapshot(state="running")
    return archiver


def test_compile_queues_the_sources_wakes_the_worker_and_answers_at_once() -> None:
    archiver = _archiver(pending=3)

    with patch(_PUBLISH, new=AsyncMock()) as publish, patch(_SCHEDULE_ASSETS) as schedule_assets:
        response = _client_for(archiver).post("/api/v1/wiki/compile?agent_id=agent-1")

    assert response.status_code == 202
    body = response.json()
    assert body["pending"] == 3
    assert body["compile_run"]["state"] == "running"
    archiver._compiler.enqueue_changed_sources.assert_awaited_once()
    archiver._compiler.start_background_worker.assert_called_once_with()
    archiver._compiler.compile_all.assert_not_called()
    publish.assert_awaited_once()
    assert publish.await_args.kwargs["agent_id"] == "agent-1"
    schedule_assets.assert_called_once_with(archiver, agent_id="agent-1")


def test_compile_counts_what_the_worker_is_already_busy_with() -> None:
    archiver = _archiver(pending=2, processing=5)

    with patch(_PUBLISH, new=AsyncMock()), patch(_SCHEDULE_ASSETS):
        response = _client_for(archiver).post("/api/v1/wiki/compile")

    assert response.json()["pending"] == 7


def test_compile_with_nothing_to_do_reports_an_empty_queue() -> None:
    archiver = _archiver()

    with patch(_PUBLISH, new=AsyncMock()), patch(_SCHEDULE_ASSETS):
        response = _client_for(archiver).post("/api/v1/wiki/compile")

    assert response.status_code == 202
    assert response.json()["pending"] == 0


def test_compile_reports_a_paused_circuit_with_its_reason() -> None:
    paused = CompileRunSnapshot(state="paused", pause_reason="Provider key was rejected", primary_error_kind="auth")
    archiver = _archiver(pending=4, run=paused)

    with patch(_PUBLISH, new=AsyncMock()), patch(_SCHEDULE_ASSETS):
        response = _client_for(archiver).post("/api/v1/wiki/compile")

    compile_run = response.json()["compile_run"]
    assert (compile_run["state"], compile_run["pause_reason"]) == ("paused", "Provider key was rejected")


def test_compile_is_refused_while_duplicates_await_review_and_queues_nothing() -> None:
    archiver = _archiver(pending=3)

    with patch(_DEDUP_BLOCKS, return_value=True):
        response = _client_for(archiver).post("/api/v1/wiki/compile")

    assert response.status_code == 409
    assert "Duplicate review required" in response.json()["detail"]
    archiver._compiler.enqueue_changed_sources.assert_not_awaited()
    archiver._compiler.start_background_worker.assert_not_called()


def test_a_failure_to_queue_is_a_generic_500_and_leaves_the_worker_asleep() -> None:
    archiver = _archiver()
    archiver._compiler.enqueue_changed_sources = AsyncMock(side_effect=RuntimeError("database is locked: /secret/path"))

    with patch(_PUBLISH, new=AsyncMock()), patch(_SCHEDULE_ASSETS):
        response = _client_for(archiver).post("/api/v1/wiki/compile")

    assert response.status_code == 500
    assert response.json()["detail"] == "Wiki compilation failed"
    archiver._compiler.start_background_worker.assert_not_called()


def test_compile_hands_a_real_vault_to_the_queue_without_a_single_model_call(tmp_path: Path) -> None:
    structure = WikiStructure(tmp_path / "wiki")
    structure.ensure_structure()
    (structure.raw_dir / "a.md").write_text("Machine learning is powerful.")
    (structure.raw_dir / "b.md").write_text("Data science content.")
    llm = AsyncMock()
    compiler = WikiCompiler(llm, structure, WikiConfig())
    archiver = SimpleNamespace(_compiler=compiler, _queue=compiler._queue)

    with (
        patch.object(compiler, "start_background_worker") as wake_worker,
        patch(_PUBLISH, new=AsyncMock()),
        patch(_SCHEDULE_ASSETS),
    ):
        response = _client_for(archiver).post("/api/v1/wiki/compile")

    assert response.status_code == 202
    assert response.json()["pending"] == 2
    assert sorted(Path(str(item["file_path"])).name for item in compiler._queue.get_pending_items(limit=10)) == [
        "a.md",
        "b.md",
    ]
    wake_worker.assert_called_once_with()
    llm.ainvoke.assert_not_called()
