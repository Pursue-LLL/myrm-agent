"""Integration tests for Dream Cognitive Consolidation and Growth Diary API endpoints.

[POS]
后台梦境认知重组与成长日记 REST API 测试套件。
端到端验证跨会话高阶洞察提取、具身自省日记生成、Markdown 视图检索与 Memory Cube 空间过滤。
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.memory.dream_cognitive_router import router as dream_cognitive_router
from app.services.memory.dream_cognitive_service import get_dream_cognitive_service


@pytest.fixture
def test_app() -> FastAPI:
    """Create isolated FastAPI app mounting dream cognitive router."""
    api_app = FastAPI()
    api_app.include_router(dream_cognitive_router, prefix="/api/memory")
    return api_app


@pytest.fixture(autouse=True)
def reset_service() -> None:
    """Reset dream cognitive service state before each test."""
    service = get_dream_cognitive_service()
    with service._lock:
        service._diaries.clear()
        service._latest_run_id = None


@pytest.mark.asyncio
async def test_trigger_cognitive_consolidation_api(test_app: FastAPI) -> None:
    """Verify that multi-session fragments trigger cognitive consolidation, deductions, and diaries."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "fragments": [
                {
                    "session_id": "sess_1",
                    "project_id": "proj_frontend",
                    "chat_turn_count": 5,
                    "memories": [
                        {
                            "fact_id": "f1",
                            "content": "Mandate TailwindCSS for all responsive layout components",
                            "evidence": [
                                {
                                    "message_id": "m1",
                                    "speaker": "user",
                                    "verbatim_quote": "Always use TailwindCSS for layout",
                                }
                            ],
                        },
                        {
                            "fact_id": "f2",
                            "content": "Prefer SVG icons over web fonts",
                        },
                    ],
                },
                {
                    "session_id": "sess_2",
                    "project_id": "proj_frontend",
                    "chat_turn_count": 3,
                    "memories": [
                        {
                            "fact_id": "f3",
                            "content": "Enforce TailwindCSS utility class conventions across project",
                            "evidence": [
                                {
                                    "message_id": "m2",
                                    "speaker": "user",
                                    "verbatim_quote": "Keep TailwindCSS conventions strictly",
                                }
                            ],
                        }
                    ],
                },
            ],
            "cube_id": "cube_frontend_rules",
            "target_project_id": "proj_frontend",
        }

        res = await client.post("/api/memory/dream-cognitive/consolidate", json=payload)
        assert res.status_code == 200
        data = res.json()

        assert data["cube_id"] == "cube_frontend_rules"
        assert data["clusters_formed"] >= 1
        assert data["actions_generated"] >= 1
        assert len(data["diary_entries"]) >= 1

        entry = data["diary_entries"][0]
        assert "diary_" in entry["diary_id"]
        assert len(entry["reflective_narrative"]) > 20
        assert entry["cube_id"] == "cube_frontend_rules"

        # Check action deduction
        action = entry["generated_actions"][0]
        assert len(action["deduction"]["hypothetical_query"]) > 0
        assert len(action["deduction"]["improved_response_reasoning"]) > 0
        assert action["confidence"] > 0.8


@pytest.mark.asyncio
async def test_list_and_get_growth_diaries_api(test_app: FastAPI) -> None:
    """Verify listing diaries, fetching single entry details, and markdown rendering."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Trigger run first
        payload = {
            "fragments": [
                {
                    "session_id": "sess_arch",
                    "chat_turn_count": 4,
                    "memories": [
                        {"content": "Refactoring must never compromise pure architecture"},
                        {"content": "Reject backward compatibility technical debt during refactoring"},
                    ],
                }
            ],
            "cube_id": "cube_architecture",
        }
        res_post = await client.post("/api/memory/dream-cognitive/consolidate", json=payload)
        assert res_post.status_code == 200
        post_data = res_post.json()
        diary_id = post_data["diary_entries"][0]["diary_id"]

        # 2. List diaries
        res_list = await client.get("/api/memory/dream-cognitive/diaries")
        assert res_list.status_code == 200
        list_data = res_list.json()
        assert len(list_data) >= 1
        assert list_data[0]["diary_id"] == diary_id

        # 3. Get single diary
        res_get = await client.get(f"/api/memory/dream-cognitive/diaries/{diary_id}")
        assert res_get.status_code == 200
        assert res_get.json()["diary_id"] == diary_id

        # 4. Get formatted markdown
        res_md = await client.get(f"/api/memory/dream-cognitive/diaries/{diary_id}/markdown")
        assert res_md.status_code == 200
        assert "text/markdown" in res_md.headers["content-type"]
        md_text = res_md.text
        assert "# 📔 智能体心智演进日记:" in md_text
        assert "### 🧠 具身心智自省 (Reflective Narrative)" in md_text

        # 5. Non-existent diary should return 404
        res_404 = await client.get("/api/memory/dream-cognitive/diaries/non_existent_diary")
        assert res_404.status_code == 404


@pytest.mark.asyncio
async def test_cognitive_overview_and_scoped_cube_filtering_api(test_app: FastAPI) -> None:
    """Verify overview metrics and filtering diaries by Memory Cube identifier."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Seed two runs with different cubes
        payload_a = {
            "fragments": [
                {"session_id": "sa", "memories": [{"content": "Cube A knowledge fact"}]}
            ],
            "cube_id": "cube_alpha",
        }
        payload_b = {
            "fragments": [
                {"session_id": "sb", "memories": [{"content": "Cube B knowledge fact"}]}
            ],
            "cube_id": "cube_beta",
        }
        await client.post("/api/memory/dream-cognitive/consolidate", json=payload_a)
        await client.post("/api/memory/dream-cognitive/consolidate", json=payload_b)

        # Overview
        res_overview = await client.get("/api/memory/dream-cognitive/overview")
        assert res_overview.status_code == 200
        overview = res_overview.json()
        assert overview["total_diaries"] >= 2
        assert "cube_alpha" in overview["active_cubes"]
        assert "cube_beta" in overview["active_cubes"]

        # Scoped filter
        res_filtered = await client.get("/api/memory/dream-cognitive/diaries?cube_id=cube_alpha")
        assert res_filtered.status_code == 200
        filtered = res_filtered.json()
        assert all(d["cube_id"] == "cube_alpha" for d in filtered)
