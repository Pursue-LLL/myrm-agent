"""Governance workbench endpoints run on a real archiver: overview, archive and revive reach the vault index."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient
from myrm_agent_harness.toolkits.wiki import WikiStructure

from app.api.dependencies import get_optional_llm_for_user
from app.core.security.auth.identity import LOCAL_USER_ID
from tests.support.minimal_app import build_minimal_app
from tests.support.wiki_compile_probe import ReachableModel, isolated_wiki_vault, write_concept


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


@pytest.fixture
def structure(tmp_path) -> Iterator[WikiStructure]:
    with isolated_wiki_vault(tmp_path) as vault:
        yield vault


@pytest.fixture
def client() -> AsyncClient:
    app = build_minimal_app(preset="wiki")
    model = ReachableModel()
    app.dependency_overrides[get_optional_llm_for_user] = lambda: model
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_overview_counts_the_active_concepts(client: AsyncClient, structure: WikiStructure) -> None:
    write_concept(structure, "topic", sources=[])

    async with client:
        response = await client.get("/api/v1/wiki/governance/overview")

    assert response.status_code == 200, response.text
    assert response.json()["total_active"] == 1


async def test_archive_then_revive_moves_the_concept_through_the_index(client: AsyncClient, structure: WikiStructure) -> None:
    concept = write_concept(structure, "topic", sources=[])

    async with client:
        archived = await client.post("/api/v1/wiki/governance/archive", json={"concept_names": ["topic"]})
        assert archived.status_code == 200, archived.text
        assert archived.json()["success"] is True
        assert not concept.exists()

        revived = await client.post("/api/v1/wiki/governance/revive", json={"concept_names": ["topic"]})
        assert revived.status_code == 200, revived.text
        assert revived.json()["success"] is True
        assert concept.exists()
