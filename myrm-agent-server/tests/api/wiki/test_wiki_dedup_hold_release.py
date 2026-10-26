"""A document held back for duplicate review is compiled by the user's model once its group is resolved."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient
from myrm_agent_harness.toolkits.wiki import WikiIngestionQueue, WikiStructure
from myrm_agent_harness.toolkits.wiki.pipeline.corpus_dedup import CorpusDedupStore, GroupStatus

from app.api.dependencies import get_optional_llm_for_user
from app.core.security.auth.identity import LOCAL_USER_ID
from app.services.wiki import dedup_runner
from app.services.wiki.memory_to_wiki import MemoryToWikiArchiver
from app.services.wiki.source_sync.deferred_enqueue import DeferredCompileEnqueue
from app.services.wiki.vault import get_wiki_archiver
from tests.support.minimal_app import build_minimal_app
from tests.support.wiki_compile_probe import (
    DUPLICATE_BODY,
    ReachableModel,
    isolated_wiki_vault,
    wait_until_queue_idle,
    write_raw,
)


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


@pytest.fixture(autouse=True)
def _no_leftover_scans() -> Iterator[None]:
    dedup_runner._running_scans.clear()
    yield
    dedup_runner._running_scans.clear()


@pytest.fixture
def structure(tmp_path: Path) -> Iterator[WikiStructure]:
    with isolated_wiki_vault(tmp_path) as vault:
        yield vault


@pytest.fixture
def model() -> ReachableModel:
    return ReachableModel()


@pytest.fixture
def archiver(structure: WikiStructure, model: ReachableModel) -> MemoryToWikiArchiver:
    return get_wiki_archiver(model)


@pytest.fixture
def client(model: ReachableModel) -> AsyncClient:
    app = build_minimal_app(preset="wiki")
    app.dependency_overrides[get_optional_llm_for_user] = lambda: model
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


PAIR = ("ima/KB1/report.md", "ima/KB2/report-copy.md")


async def _import_a_pair_the_scan_flags(archiver: MemoryToWikiArchiver) -> int:
    """Publish two identical documents the way a connector run does and return the id of the group the scan opens."""
    structure = archiver._structure
    deferred = DeferredCompileEnqueue(archiver._compiler, structure)
    for relative_path in PAIR:
        deferred.enqueue_file(write_raw(structure, relative_path, DUPLICATE_BODY))
    assert await dedup_runner.run_post_sync_dedup_scan(agent_id=None)

    assert await deferred.release(scan_completed=True) == 0
    (group,) = CorpusDedupStore(structure).list_groups(status=GroupStatus.OPEN)
    return group.group_id


def _compiled_names(structure: WikiStructure) -> list[str]:
    """The sources the worker picked up (it fails every one of them on the stand-in model)."""
    return sorted(Path(item["file_path"]).name for item in WikiIngestionQueue(structure).get_failed_items())


async def test_a_held_duplicate_is_compiled_once_the_user_trashes_its_copy(
    client: AsyncClient, structure: WikiStructure, archiver: MemoryToWikiArchiver, model: ReachableModel
) -> None:
    group_id = await _import_a_pair_the_scan_flags(archiver)
    assert WikiIngestionQueue(structure).get_stats() == {"pending": 0, "processing": 0, "completed": 0, "failed": 0}
    assert model.reached == []

    async with client:
        resolved = await client.post(
            f"/api/v1/wiki/dedup/groups/{group_id}/disposition", json={"action": "trash", "reason": "same report"}
        )
        assert resolved.status_code == 200, resolved.text
        await wait_until_queue_idle(structure)

    survivors = [Path(relative_path).name for relative_path in PAIR if structure.get_raw_file_path(relative_path).exists()]
    assert len(survivors) == 1
    assert _compiled_names(structure) == survivors
    assert set(model.reached) == {"ainvoke"}


async def test_dismissing_a_group_compiles_both_documents(
    client: AsyncClient, structure: WikiStructure, archiver: MemoryToWikiArchiver, model: ReachableModel
) -> None:
    group_id = await _import_a_pair_the_scan_flags(archiver)

    async with client:
        resolved = await client.post(f"/api/v1/wiki/dedup/groups/{group_id}/disposition", json={"action": "dismiss"})
        assert resolved.status_code == 200, resolved.text
        await wait_until_queue_idle(structure)

    assert _compiled_names(structure) == ["report-copy.md", "report.md"]
    assert set(model.reached) == {"ainvoke"}
