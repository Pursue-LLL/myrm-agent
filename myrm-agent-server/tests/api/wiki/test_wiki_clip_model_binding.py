"""A clip queued for compiling is compiled with the user's model, whichever request woke the worker."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from dataclasses import dataclass
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient
from myrm_agent_harness.toolkits.wiki import WikiIngestionQueue, WikiStructure

from app.api.dependencies import get_optional_llm_for_user
from app.core.security.auth.identity import LOCAL_USER_ID
from app.services.wiki import dedup_runner
from tests.support.minimal_app import build_minimal_app
from tests.support.wiki_compile_probe import (
    ReachableModel,
    clear_compile_workers,
    isolated_wiki_vault,
    wait_until_queue_idle,
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


async def _wait_for_clip_job(client: AsyncClient, job_id: str) -> dict[str, object]:
    for _ in range(200):
        status = (await client.get(f"/api/v1/wiki/clip/{job_id}")).json()
        if status["state"] in {"succeeded", "failed"}:
            return status
        await asyncio.sleep(0.02)
    raise AssertionError("clip job did not finish")


async def test_clip_queued_for_compile_runs_with_the_users_model(
    client: AsyncClient, structure: WikiStructure, model: ReachableModel
) -> None:
    async with client:
        assert (await client.get("/api/v1/wiki/stats")).status_code == 200
        clear_compile_workers()

        accepted = await client.post(
            "/api/v1/wiki/clip",
            data={
                "source_url": "https://example.com/article",
                "title": "Article",
                "markdown": "# Article\n\nBody worth compiling.",
                "queue_compile": "true",
            },
        )
        assert accepted.status_code == 202, accepted.text
        job = await _wait_for_clip_job(client, accepted.json()["job_id"])
        assert job["state"] == "succeeded", job
        await wait_until_queue_idle(structure)

    assert set(model.reached) == {"ainvoke"}
    failures = [item["error_message"] or "" for item in WikiIngestionQueue(structure).get_failed_items()]
    assert not [message for message in failures if "NoneType" in message]


async def test_wikiignore_is_read_and_written_without_a_model(client: AsyncClient, structure: WikiStructure) -> None:
    with patch("app.services.wiki.vault.get_wiki_archiver", side_effect=AssertionError("built an archiver for wikiignore")):
        async with client:
            updated = await client.put("/api/v1/wiki/wikiignore", json={"content": "drafts/**\n"})
            assert updated.status_code == 200, updated.text
            read = await client.get("/api/v1/wiki/wikiignore")

    assert "drafts/**" in read.json()["content"]
    assert structure.load_wikiignore_patterns() == ("drafts/**",)
