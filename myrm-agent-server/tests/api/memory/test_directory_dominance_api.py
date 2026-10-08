"""[POS]: tests/api/memory/test_directory_dominance_api.py
[INPUT]: FastAPI TestClient and directory dominance endpoints.
[OUTPUT]: Pytest integration tests verifying dominance evaluation and hierarchical retrieval with sibling bundling.
"""

from collections.abc import AsyncGenerator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.memory.directory_dominance_router import (
    router as directory_dominance_router,
)
from app.services.memory.directory_dominance_service import (
    DirectoryDominanceService,
    get_directory_dominance_service,
)


@pytest.fixture
def app() -> FastAPI:
    """Create isolated FastAPI instance mounting directory dominance router."""
    test_app = FastAPI()
    test_app.include_router(directory_dominance_router)
    test_app.dependency_overrides[get_directory_dominance_service] = (
        lambda: DirectoryDominanceService()
    )
    return test_app


@pytest.fixture
async def client(app: FastAPI) -> AsyncGenerator[AsyncClient, None]:
    """Create async HTTP client for FastAPI test app."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac


@pytest.mark.anyio
async def test_evaluate_dominance_api(client: AsyncClient) -> None:
    """Verify REST endpoint evaluating directory dominance ratios."""
    # 1. Directory dominant case: dir_score=0.90 >= 0.70 * 1.2 (= 0.84)
    payload_dominant = {
        "dir_node": {
            "uri": "context://resources/auth/",
            "node_type": "directory",
            "name": "auth",
            "score": 0.90,
        },
        "children_nodes": [
            {
                "uri": "context://resources/auth/oauth.py",
                "node_type": "file",
                "name": "oauth.py",
                "score": 0.70,
            },
            {
                "uri": "context://resources/auth/jwt.py",
                "node_type": "file",
                "name": "jwt.py",
                "score": 0.65,
            },
        ],
        "dominance_ratio": 1.2,
    }
    resp = await client.post("/directory-dominance/evaluate-dominance", json=payload_dominant)
    assert resp.status_code == 200
    data = resp.json()
    assert data["decision"] == "directory_dominant"
    assert data["required_threshold"] == pytest.approx(0.84)

    # 2. Leaf specific case: child score exceeds directory
    payload_leaf = {
        "dir_node": {
            "uri": "context://resources/auth/",
            "node_type": "directory",
            "name": "auth",
            "score": 0.50,
        },
        "children_nodes": [
            {
                "uri": "context://resources/auth/oauth.py",
                "node_type": "file",
                "name": "oauth.py",
                "score": 0.85,
            }
        ],
        "dominance_ratio": 1.2,
    }
    resp_leaf = await client.post("/directory-dominance/evaluate-dominance", json=payload_leaf)
    assert resp_leaf.status_code == 200
    assert resp_leaf.json()["decision"] == "leaf_specific"


@pytest.mark.anyio
async def test_retrieve_hierarchical_macro_dominance_api(client: AsyncClient) -> None:
    """Verify macro intent retrieval correctly returns dominant directory."""
    payload = {
        "query": "system architecture blueprint",
        "nodes": [
            {
                "uri": "context://resources/architecture/",
                "node_type": "directory",
                "name": "architecture",
                "abstract": "High-level architectural blueprint.",
                "content": "Overall system components and boundaries.",
                "score": 0.96,
            },
            {
                "uri": "context://resources/architecture/micro.md",
                "node_type": "file",
                "name": "micro.md",
                "parent_uri": "context://resources/architecture/",
                "abstract": "Micro service specs.",
                "score": 0.65,
            },
        ],
        "limit": 5,
        "dominance_ratio": 1.2,
    }
    resp = await client.post("/directory-dominance/retrieve", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["hits"]) == 1
    hit = data["hits"][0]
    assert hit["uri"] == "context://resources/architecture/"
    assert hit["decision"] == "directory_dominant"
    assert data["stats"]["dominant_directories_count"] == 1


@pytest.mark.anyio
async def test_retrieve_hierarchical_leaf_sibling_bundling_api(client: AsyncClient) -> None:
    """Verify localized file hits automatically bundle sibling abstracts and parent context."""
    payload = {
        "query": "oauth grant flow implementation",
        "nodes": [
            {
                "uri": "context://resources/auth/",
                "node_type": "directory",
                "name": "auth",
                "abstract": "Auth system umbrella overview.",
                "score": 0.45,
            },
            {
                "uri": "context://resources/auth/oauth.py",
                "node_type": "file",
                "name": "oauth.py",
                "parent_uri": "context://resources/auth/",
                "abstract": "OAuth handler.",
                "content": "def oauth(): pass",
                "score": 0.95,
            },
            {
                "uri": "context://resources/auth/jwt.py",
                "node_type": "file",
                "name": "jwt.py",
                "parent_uri": "context://resources/auth/",
                "abstract": "JWT token issuer.",
                "score": 0.70,
            },
            {
                "uri": "context://resources/auth/session.py",
                "node_type": "file",
                "name": "session.py",
                "parent_uri": "context://resources/auth/",
                "abstract": "Session store.",
                "score": 0.68,
            },
        ],
        "limit": 5,
        "dominance_ratio": 1.2,
        "max_siblings_per_hit": 2,
    }
    resp = await client.post("/directory-dominance/retrieve", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["hits"]) >= 1
    top_hit = data["hits"][0]
    assert top_hit["uri"] == "context://resources/auth/oauth.py"
    assert top_hit["decision"] == "leaf_specific"
    assert "Auth system umbrella" in (top_hit["parent_summary"] or "")
    assert len(top_hit["sibling_contexts"]) == 2
    sibling_uris = [sib["uri"] for sib in top_hit["sibling_contexts"]]
    assert "context://resources/auth/jwt.py" in sibling_uris
    assert "context://resources/auth/session.py" in sibling_uris
