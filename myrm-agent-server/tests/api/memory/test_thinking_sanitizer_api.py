# [POS]: tests/api/memory/test_thinking_sanitizer_api.py
# [INPUT]: app.api.memory.thinking_sanitizer_router, FastAPI app
# [OUTPUT]: Integration API tests for Thinking Block Sanitizer & Prompt Contamination Shield (Item 115)

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.memory.thinking_sanitizer_router import (
    router as thinking_sanitizer_router,
)
from app.services.memory.thinking_sanitizer_service import (
    ThinkingSanitizerService,
    get_thinking_sanitizer_service,
)


@pytest.fixture
def isolated_service() -> ThinkingSanitizerService:
    """Provides an isolated ThinkingSanitizerService instance."""
    return ThinkingSanitizerService()


@pytest.fixture
def test_app(isolated_service: ThinkingSanitizerService) -> FastAPI:
    """Creates a lightweight test FastAPI application with dependency overrides."""
    app = FastAPI()
    app.include_router(thinking_sanitizer_router, prefix="/api/memory")
    app.dependency_overrides[get_thinking_sanitizer_service] = lambda: isolated_service
    return app


@pytest.mark.asyncio
async def test_sanitize_api_paired_and_orphan_tags(test_app: FastAPI) -> None:
    """Validate scrubbing paired thinking blocks and orphan close tags via API."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Paired thinking tags
        raw_text = (
            "<think>Analyzing session context...</think>\n"
            "The cluster nodes successfully synchronized state."
        )
        res_paired = await client.post(
            "/api/memory/thinking-sanitizer/sanitize",
            json={"text": raw_text},
        )
        assert res_paired.status_code == 200
        data_paired = res_paired.json()
        assert data_paired["has_thinking_markers"] is True
        assert data_paired["has_unclosed_tags"] is False
        assert data_paired["is_usable"] is True
        assert "<think>" not in data_paired["cleaned_text"]
        assert "The cluster nodes successfully synchronized state." in data_paired["cleaned_text"]

        # 2. Orphan </think> close tag rescue
        orphan_text = (
            "Thinking about caching policy...\n"
            "</think>\n"
            "Cache expiration was reduced from 300s to 60s."
        )
        res_orphan = await client.post(
            "/api/memory/thinking-sanitizer/sanitize",
            json={"text": orphan_text},
        )
        assert res_orphan.status_code == 200
        data_orphan = res_orphan.json()
        assert data_orphan["has_thinking_markers"] is True
        assert data_orphan["cleaned_text"] == "Cache expiration was reduced from 300s to 60s."
        assert data_orphan["is_usable"] is True


@pytest.mark.asyncio
async def test_sanitize_api_unclosed_tags_and_configuration(test_app: FastAPI) -> None:
    """Validate unclosed tags handling and custom configuration via API."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Unclosed tag dropping content
        unclosed_text = "<think>Drafting ideas that never finished..."
        res_unclosed = await client.post(
            "/api/memory/thinking-sanitizer/sanitize",
            json={
                "text": unclosed_text,
                "config": {
                    "min_usable_chars": 10,
                    "drop_unclosed_tags": True,
                },
            },
        )
        assert res_unclosed.status_code == 200
        data_unclosed = res_unclosed.json()
        assert data_unclosed["has_unclosed_tags"] is True
        assert data_unclosed["is_usable"] is False
        assert data_unclosed["cleaned_text"] == ""
        assert data_unclosed["rejection_reason"] is not None


@pytest.mark.asyncio
async def test_usable_summary_check_api(test_app: FastAPI) -> None:
    """Validate bi-directional egress summary usability checking via API."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Valid summary returns is_usable=True and clean summary
        valid_payload = {
            "text": "<thought>Summary thoughts</thought>\nCore infrastructure migration completed without downtime.",
        }
        res_valid = await client.post(
            "/api/memory/thinking-sanitizer/usable-check",
            json=valid_payload,
        )
        assert res_valid.status_code == 200
        data_valid = res_valid.json()
        assert data_valid["is_usable"] is True
        assert data_valid["summary"] == "Core infrastructure migration completed without downtime."
        assert data_valid["rejection_reason"] is None

        # Pure thought draft returns is_usable=False and summary=None
        pure_draft = {
            "text": "<thought>Still pondering what to do next...</thought>",
        }
        res_invalid = await client.post(
            "/api/memory/thinking-sanitizer/usable-check",
            json=pure_draft,
        )
        assert res_invalid.status_code == 200
        data_invalid = res_invalid.json()
        assert data_invalid["is_usable"] is False
        assert data_invalid["summary"] is None
        assert data_invalid["rejection_reason"] is not None
