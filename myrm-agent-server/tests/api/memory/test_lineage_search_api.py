# [POS]: tests/api/memory/test_lineage_search_api.py
# [INPUT]: Isolated FastAPI test application, AsyncClient, and temporary SQLite database file.
# [OUTPUT]: Integration tests verifying session registration, cron demotion, lineage dedup, and hydration APIs.

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.memory.lineage_search_router import router as lineage_search_router
from app.services.memory.lineage_search_service import (
    LineageSearchService,
    get_lineage_search_service,
)


@pytest.fixture
def isolated_service(tmp_path: Path) -> LineageSearchService:
    """Provides an isolated LineageSearchService backed by temporary SQLite DB."""
    db_file = tmp_path / "test_lineage_api.db"
    return LineageSearchService(db_path=db_file)


@pytest.fixture
def test_app(isolated_service: LineageSearchService) -> FastAPI:
    """Creates a FastAPI test application with dependency overrides."""
    app = FastAPI()
    app.include_router(lineage_search_router, prefix="/api/memory")
    app.dependency_overrides[get_lineage_search_service] = lambda: isolated_service
    return app


@pytest.mark.asyncio
async def test_session_and_message_registration_api(test_app: FastAPI) -> None:
    """Verifies registering sessions and recording messages via REST APIs."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Register session
        res_sess = await client.post(
            "/api/memory/lineage-search/sessions",
            json={
                "session": {
                    "session_id": "sess_api_001",
                    "title": "Architecture Review",
                    "source": "interactive",
                    "lineage_root_id": "root_api_001",
                    "model": "gpt-4o",
                }
            },
        )
        assert res_sess.status_code == 200
        data_sess = res_sess.json()
        assert data_sess["is_success"] is True
        assert data_sess["session_id"] == "sess_api_001"

        # 2. Add messages
        res_msg = await client.post(
            "/api/memory/lineage-search/messages",
            json={
                "message": {
                    "message_id": "msg_001",
                    "session_id": "sess_api_001",
                    "role": "user",
                    "content": "Let us review memory FTS5 indexing architecture.",
                    "sequence_num": 1,
                }
            },
        )
        assert res_msg.status_code == 200
        assert res_msg.json()["is_success"] is True

        # 3. Fetch session messages
        res_msgs = await client.get("/api/memory/lineage-search/sessions/sess_api_001/messages")
        assert res_msgs.status_code == 200
        msgs_data = res_msgs.json()
        assert len(msgs_data) == 1
        assert msgs_data[0]["message_id"] == "msg_001"
        assert msgs_data[0]["role"] == "user"


@pytest.mark.asyncio
async def test_lineage_search_demotion_and_hydration_api(test_app: FastAPI) -> None:
    """Verifies cron demotion defense (PR #19434), lineage dedup, and two-tier adaptive hydration."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Register interactive session with 4 messages
        await client.post(
            "/api/memory/lineage-search/sessions",
            json={
                "session": {
                    "session_id": "sess_interactive_user",
                    "title": "User Performance Discussion",
                    "source": "interactive",
                    "lineage_root_id": "root_user_flow",
                }
            },
        )
        for i in range(1, 5):
            await client.post(
                "/api/memory/lineage-search/messages",
                json={
                    "message": {
                        "message_id": f"msg_u_{i}",
                        "session_id": "sess_interactive_user",
                        "role": "user" if i % 2 == 1 else "assistant",
                        "content": f"Optimizing database throughput step {i} with FTS5.",
                        "sequence_num": i,
                    }
                },
            )

        # 2. Register cron session with high keyword density
        await client.post(
            "/api/memory/lineage-search/sessions",
            json={
                "session": {
                    "session_id": "sess_cron_sweep",
                    "title": "Nightly Database Optimizer",
                    "source": "cron",
                    "lineage_root_id": "root_cron_flow",
                }
            },
        )
        await client.post(
            "/api/memory/lineage-search/messages",
            json={
                "message": {
                    "message_id": "msg_c_1",
                    "session_id": "sess_cron_sweep",
                    "role": "assistant",
                    "content": "Automated sweep: optimizing database vacuum and FTS5 indexes completed.",
                    "sequence_num": 1,
                }
            },
        )

        # 3. Search query: "optimizing database"
        res_search = await client.post(
            "/api/memory/lineage-search/search",
            json={
                "query": "optimizing database",
                "limit": 5,
                "anchor_window": 2,
                "bookend_count": 1,
            },
        )
        assert res_search.status_code == 200
        search_data = res_search.json()
        assert search_data["total_hits"] == 2

        # Verification of PR #19434 recall blindness defense:
        # Interactive session MUST rank first, cron MUST be demoted
        hits = search_data["results"]
        assert hits[0]["session_id"] == "sess_interactive_user"
        assert hits[0]["source"] == "interactive"
        assert hits[0]["detail_level"] == "full"  # Top 1 receives full window
        assert len(hits[0]["window_messages"]) >= 1
        assert "@session:sess_interactive_user#msg_" in hits[0]["deep_link"]

        # Top 2 (cron hit) receives compact card detail
        assert hits[1]["session_id"] == "sess_cron_sweep"
        assert hits[1]["source"] == "cron"
        assert hits[1]["detail_level"] == "compact"
        assert len(hits[1]["bookend_start"]) == 0

        # 4. Telemetry stats check
        res_stats = await client.get("/api/memory/lineage-search/stats")
        assert res_stats.status_code == 200
        stats_data = res_stats.json()
        assert stats_data["total_sessions"] == 2
        assert stats_data["demoted_sources_count"] == 1
