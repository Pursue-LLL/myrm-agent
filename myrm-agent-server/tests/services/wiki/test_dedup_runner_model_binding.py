"""Duplicate review compiles through the user's model, and dedup reads and scans build no archiver."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient
from myrm_agent_harness.toolkits.wiki import WikiIngestionQueue, WikiStructure
from myrm_agent_harness.toolkits.wiki.pipeline.corpus_dedup import CorpusDedupGovernor, DispositionAction

from app.api.dependencies import get_optional_llm_for_user
from app.core.security.auth.identity import LOCAL_USER_ID
from app.services.wiki import dedup_runner
from tests.support.minimal_app import build_minimal_app
from tests.support.wiki_compile_probe import (
    ReachableModel,
    clear_compile_workers,
    isolated_wiki_vault,
    seed_open_group,
    wait_until_queue_idle,
    write_concept,
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
def structure(tmp_path) -> Iterator[WikiStructure]:
    with isolated_wiki_vault(tmp_path) as vault:
        yield vault


@pytest.fixture
def model() -> ReachableModel:
    return ReachableModel()


@pytest.fixture
def client(model: ReachableModel) -> AsyncClient:
    app = build_minimal_app(preset="wiki")
    app.dependency_overrides[get_optional_llm_for_user] = lambda: model
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _until(condition: Callable[[], bool], *, timeout_s: float = 10.0) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_s
    while not condition():
        if loop.time() >= deadline:
            raise AssertionError("condition not met in time")
        await asyncio.sleep(0.02)


async def test_disposition_compiles_the_surviving_source_with_the_users_model(
    client: AsyncClient, structure: WikiStructure, model: ReachableModel
) -> None:
    write_concept(structure, "quarterly-report", sources=["reports/a.md", "reports/b.md"])
    group = seed_open_group(structure, "reports/a.md", "reports/b.md")

    async with client:
        # An earlier request built the archiver with the user's model; its compile worker has idled out since.
        assert (await client.get("/api/v1/wiki/stats")).status_code == 200
        clear_compile_workers()

        response = await client.post(
            f"/api/v1/wiki/dedup/groups/{group.group_id}/disposition",
            json={"action": "trash", "reason": "same document"},
        )
        assert response.status_code == 200, response.text
        await wait_until_queue_idle(structure)

    assert set(model.reached) == {"ainvoke"}
    failures = [item["error_message"] or "" for item in WikiIngestionQueue(structure).get_failed_items()]
    assert not [message for message in failures if "NoneType" in message]


async def test_restoring_a_trashed_source_compiles_it_with_the_users_model(
    client: AsyncClient, structure: WikiStructure, model: ReachableModel
) -> None:
    group = seed_open_group(structure, "reports/a.md", "reports/b.md")
    governor = CorpusDedupGovernor(structure)
    await governor.apply_disposition(group.group_id, DispositionAction.TRASH, reason="same document")
    (trashed,) = governor.list_vault_hygiene().trashed

    async with client:
        assert (await client.get("/api/v1/wiki/stats")).status_code == 200
        clear_compile_workers()

        response = await client.post("/api/v1/wiki/dedup/trash/restore", json={"relative_path": trashed.relative_path})
        assert response.status_code == 200, response.text
        await wait_until_queue_idle(structure)

    assert set(model.reached) == {"ainvoke"}
    failures = [item["error_message"] or "" for item in WikiIngestionQueue(structure).get_failed_items()]
    assert not [message for message in failures if "NoneType" in message]


async def test_dedup_reads_and_scans_build_no_archiver(structure: WikiStructure) -> None:
    seed_open_group(structure, "reports/a.md", "reports/b.md")
    governor = CorpusDedupGovernor(structure)
    governor.store.dispositions.add_excluded_path("reports/c.md", reason="manual")

    with patch(
        "app.services.wiki.vault.get_wiki_archiver",
        side_effect=AssertionError("built an archiver for a dedup read or scan"),
    ):
        job = await dedup_runner.run_wiki_dedup_scan_job(incremental=False)
        assert job.scan_result is not None
        assert job.scan_result.open_groups == 1
        assert dedup_runner.wiki_dedup_blocks_compile() is True
        assert dedup_runner.wiki_dedup_checklist_ready() is False
        assert dedup_runner.get_wiki_dedup_stats().duplicate_groups_pending == 1
        assert dedup_runner.get_wiki_dedup_progress().phase == "done"
        (listed,) = dedup_runner.list_wiki_dedup_groups()
        assert len(dedup_runner.get_wiki_dedup_group_snippets(agent_id=None, group_id=listed.group_id)) == 2
        assert [entry.relative_path for entry in dedup_runner.get_wiki_dedup_vault_hygiene().excluded] == ["reports/c.md"]

        # Undoing an exclusion schedules a rescan of its own; let it finish before scheduling another.
        await dedup_runner.undo_wiki_dedup_excluded(agent_id=None, relative_path="reports/c.md")
        await _until(lambda: not dedup_runner.is_wiki_dedup_scan_running())

        scheduled = await dedup_runner.schedule_wiki_dedup_scan(incremental=False)
        assert scheduled.accepted is True
        await _until(lambda: not dedup_runner.is_wiki_dedup_scan_running())
        assert dedup_runner.get_wiki_dedup_progress().phase == "done"
