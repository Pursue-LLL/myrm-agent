"""End-to-end integration test for /v1/chat/completions.

Uses real LLM model (no mocks). Requires BASIC_API_KEY and BASIC_MODEL env vars.
Verifies the full request path: auth → param assembly → Agent execution → response.
"""

import json
import os

import pytest
from dotenv import load_dotenv
from httpx import ASGITransport, AsyncClient

from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="openai_compat_only", openai_compat=True)
load_dotenv(override=False)

BASIC_API_KEY = os.getenv("BASIC_API_KEY", "")
BASIC_MODEL = os.getenv("BASIC_MODEL", "")

pytestmark = [
    pytest.mark.skipif(
        not BASIC_API_KEY or not BASIC_MODEL,
        reason="BASIC_API_KEY and BASIC_MODEL required for E2E tests",
    ),
    pytest.mark.skipif(
        not os.getenv("RUN_OPENAI_COMPAT_E2E"),
        reason="Set RUN_OPENAI_COMPAT_E2E=1 with a running server to enable",
    ),
]


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
async def api_key(client: AsyncClient) -> str:
    """Create a real API key for E2E testing."""
    resp = await client.post("/api/v1/api-keys", json={"name": "E2E Real Test"})
    assert resp.status_code == 200
    return resp.json()["key"]


@pytest.mark.asyncio
@pytest.mark.timeout(120)
async def test_e2e_non_streaming(client: AsyncClient, api_key: str):
    """Full end-to-end non-streaming request with real LLM."""
    resp = await client.post(
        "/v1/chat/completions",
        json={
            "model": "default",
            "messages": [
                {"role": "user", "content": "Reply with exactly: HELLO_E2E_TEST"},
            ],
            "stream": False,
            "temperature": 0,
        },
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=100,
    )

    assert resp.status_code == 200
    data = resp.json()

    assert data["object"] == "chat.completion"
    assert data["id"].startswith("chatcmpl-")
    assert len(data["choices"]) == 1
    assert data["choices"][0]["finish_reason"] == "stop"

    content = data["choices"][0]["message"]["content"]
    assert len(content) > 0
    assert "HELLO_E2E_TEST" in content.upper().replace(" ", "_")


@pytest.mark.asyncio
@pytest.mark.timeout(120)
async def test_e2e_streaming(client: AsyncClient, api_key: str):
    """Full end-to-end streaming request with real LLM."""
    resp = await client.post(
        "/v1/chat/completions",
        json={
            "model": "default",
            "messages": [
                {"role": "user", "content": "Say hi in 3 words"},
            ],
            "stream": True,
            "temperature": 0,
        },
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=100,
    )

    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]

    lines = resp.text.strip().split("\n\n")
    chunks = []
    done_received = False

    for line in lines:
        if line == "data: [DONE]":
            done_received = True
        elif line.startswith("data: "):
            chunk = json.loads(line[6:])
            chunks.append(chunk)
            assert chunk["object"] == "chat.completion.chunk"

    assert done_received, "Stream should end with [DONE]"
    assert len(chunks) >= 2, "Should have at least role + content chunks"

    # First chunk should have role
    assert chunks[0]["choices"][0]["delta"].get("role") == "assistant"

    # Should have content chunks
    content_parts = [c["choices"][0]["delta"].get("content", "") for c in chunks if c["choices"][0]["delta"].get("content")]
    full_content = "".join(content_parts)
    assert len(full_content) > 0

    # Last meaningful chunk should have finish_reason=stop
    stop_chunks = [c for c in chunks if c["choices"][0].get("finish_reason") == "stop"]
    assert len(stop_chunks) >= 1


@pytest.mark.asyncio
@pytest.mark.timeout(120)
async def test_e2e_models_endpoint(client: AsyncClient, api_key: str):
    """GET /v1/models should return available models including default."""
    resp = await client.get("/v1/models", headers={"Authorization": f"Bearer {api_key}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["object"] == "list"
    assert any(m["id"] == "default" for m in data["data"])
    for model in data["data"]:
        assert model["object"] == "model"
        assert model["owned_by"]
