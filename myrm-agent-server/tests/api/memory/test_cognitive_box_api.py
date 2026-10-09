"""[POS]: tests/api/memory/test_cognitive_box_api.py
[INPUT]: AsyncClient, isolated CognitiveMemoryBoxService, and cognitive box router.
[OUTPUT]: Pytest integration tests verifying intake evaluation, four-layer isolation, and snapshots.
"""

from collections.abc import AsyncGenerator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from myrm_agent_harness.toolkits.memory import (
    CognitiveMemoryBoxService,
)

from app.api.memory.cognitive_box import (
    get_cognitive_box_service,
)
from app.api.memory.cognitive_box import (
    router as cognitive_box_router,
)


@pytest.fixture
def isolated_service() -> CognitiveMemoryBoxService:
    """Create isolated CognitiveMemoryBoxService instance backed by in-memory SQLite database."""
    return CognitiveMemoryBoxService(db_path=":memory:")


@pytest.fixture
def test_app(isolated_service: CognitiveMemoryBoxService) -> FastAPI:
    """Create FastAPI test application with injected isolated cognitive box service."""
    api_app = FastAPI()
    api_app.include_router(cognitive_box_router, prefix="/api/memory")
    api_app.dependency_overrides[get_cognitive_box_service] = lambda: isolated_service
    return api_app


@pytest.fixture
async def client(test_app: FastAPI) -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP client fixture bound to isolated test app."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_evaluate_intake_noise_and_admit_api(client: AsyncClient) -> None:
    # 1. Noise rejected
    res_noise = await client.post(
        "/api/memory/cognitive-box/evaluate",
        json={"content": "hello there!", "tags": ["greeting"]},
    )
    assert res_noise.status_code == 200
    data_noise = res_noise.json()
    assert data_noise["decision"] == "drop_noise"
    assert data_noise["admitted_entry"] is None

    # 2. User profile preference admitted
    res_admit = await client.post(
        "/api/memory/cognitive-box/evaluate",
        json={
            "content": "我偏好使用 2 空格缩进，并且总是使用明确的 Type Hints",
            "source_session": "sess_web_001",
            "tags": ["coding_style"],
        },
    )
    assert res_admit.status_code == 200
    data_admit = res_admit.json()
    assert data_admit["decision"] == "admit"
    assert data_admit["layer"] == "user_profile"
    assert data_admit["admitted_entry"] is not None
    assert data_admit["admitted_entry"]["source_session"] == "sess_web_001"


@pytest.mark.asyncio
async def test_write_direct_and_snapshot_api(client: AsyncClient) -> None:
    # 1. Direct write identity
    res_id = await client.post(
        "/api/memory/cognitive-box/write",
        json={
            "layer": "identity",
            "content": "核心安全原则：绝对禁止执行任何破坏性命令",
            "confidence": 1.0,
            "tags": ["security"],
        },
    )
    assert res_id.status_code == 200
    assert res_id.json()["layer"] == "identity"

    # 2. Direct write environment
    res_env = await client.post(
        "/api/memory/cognitive-box/write",
        json={
            "layer": "environment",
            "content": "执行环境：macOS Darwin arm64 沙箱，挂载 Python 3.13 与 Node 22",
            "confidence": 0.95,
            "tags": ["env"],
        },
    )
    assert res_env.status_code == 200

    # 3. Snapshot
    res_snap = await client.get("/api/memory/cognitive-box/snapshot")
    assert res_snap.status_code == 200
    snap_data = res_snap.json()
    assert snap_data["total_count"] == 2
    assert snap_data["counts_by_layer"]["identity"] == 1
    assert snap_data["counts_by_layer"]["environment"] == 1

    # 4. Prompt context
    res_prompt = await client.get("/api/memory/cognitive-box/prompt-context")
    assert res_prompt.status_code == 200
    prompt_str = res_prompt.json()["prompt_context"]
    assert "Cognitive Layer 1: Identity & Boundaries" in prompt_str
    assert "破坏性命令" in prompt_str


@pytest.mark.asyncio
async def test_list_and_clear_layer_api(client: AsyncClient) -> None:
    # Seed entries
    await client.post(
        "/api/memory/cognitive-box/write",
        json={"layer": "lessons_rules", "content": "规则1：测试必须全绿", "tags": ["qa"]},
    )
    await client.post(
        "/api/memory/cognitive-box/write",
        json={"layer": "lessons_rules", "content": "规则2：单文件行数严格小于400行", "tags": ["refactor"]},
    )

    # List entries
    res_list = await client.get("/api/memory/cognitive-box/entries?layer=lessons_rules")
    assert res_list.status_code == 200
    assert len(res_list.json()) == 2

    # Clear layer
    res_clear = await client.delete("/api/memory/cognitive-box/layer/lessons_rules")
    assert res_clear.status_code == 200
    assert res_clear.json()["purged_count"] == 2

    # Re-check
    res_empty = await client.get("/api/memory/cognitive-box/entries?layer=lessons_rules")
    assert res_empty.status_code == 200
    assert len(res_empty.json()) == 0
