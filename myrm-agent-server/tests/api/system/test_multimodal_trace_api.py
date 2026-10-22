"""
[INPUT]:
- httpx, ASGITransport
- app.api.system.multimodal_trace_api::router

[OUTPUT]:
- Pytest verification for decoupled multimodal trace media references and in-place inspection REST endpoints.

[POS]:
tests/api/system/test_multimodal_trace_api.py — 多模态 Trace 媒体引用与三步排查 API 单元测试。
"""

from collections.abc import AsyncGenerator

from fastapi import FastAPI
import httpx
from httpx import ASGITransport
import pytest

from app.api.system.multimodal_trace_api import router as mm_router

test_app = FastAPI()
test_app.include_router(mm_router, prefix="/api/v1/system")


@pytest.fixture
async def async_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://testserver",
        headers={"Content-Type": "application/json"},
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_multimodal_trace_api_flow(async_client: httpx.AsyncClient) -> None:
    # 1. Reset all traces
    reset_resp = await async_client.post("/api/v1/system/multimodal-trace/reset")
    assert reset_resp.status_code == 200
    assert reset_resp.json() == {"ok": True}

    # 2. Register decoupled media reference
    m_resp = await async_client.post(
        "/api/v1/system/multimodal-trace/register-media",
        json={
            "media_id": "shot_login_01",
            "uri": "storage://workspace/screenshots/login.png",
            "modality": "image",
            "mime_type": "image/png",
            "file_size_bytes": 350000,
            "sha256_hash": "sha256_abcdef123456",
            "presigned_preview_url": "https://cdn.local/preview/login.png?token=exp3600",
            "visibility_state": "ready",
        },
    )
    assert m_resp.status_code == 200
    m_data = m_resp.json()
    assert m_data["media_id"] == "shot_login_01"
    assert m_data["modality"] == "image"
    assert m_data["visibility_state"] == "ready"

    # 3. Update visibility state to uploading
    vis_resp = await async_client.post(
        "/api/v1/system/multimodal-trace/update-visibility",
        json={
            "media_id": "shot_login_01",
            "visibility_state": "uploading",
        },
    )
    assert vis_resp.status_code == 200

    # 4. Record multimodal trace with 3-step inspector stages
    tr_resp = await async_client.post(
        "/api/v1/system/multimodal-trace/record-trace",
        json={
            "trace_id": "tr_multimodal_001",
            "session_id": "sess_ui_bug",
            "prompt_summary": "Fix broken button layout in login dialog",
            "media_ids": ["shot_login_01"],
            "steps": [
                {
                    "step_index": 1,
                    "step_type": "input",
                    "description": "User uploaded login screenshot showing overlapping button",
                    "media_ids": ["shot_login_01"],
                    "status": "success",
                },
                {
                    "step_index": 2,
                    "step_type": "execution",
                    "description": "Applied flex-wrap and gap-2 to button container",
                    "media_ids": [],
                    "status": "success",
                },
                {
                    "step_index": 3,
                    "step_type": "feedback",
                    "description": "Visual snapshot diff passed; user approved",
                    "media_ids": [],
                    "status": "success",
                },
            ],
        },
    )
    assert tr_resp.status_code == 200
    tr_data = tr_resp.json()
    assert tr_data["trace_id"] == "tr_multimodal_001"
    assert len(tr_data["media_references"]) == 1
    assert len(tr_data["steps"]) == 3
    assert tr_data["pinned_for_golden_eval"] is False

    # 5. Query single trace
    get_tr = await async_client.get("/api/v1/system/multimodal-trace/trace/tr_multimodal_001")
    assert get_tr.status_code == 200
    assert get_tr.json()["prompt_summary"] == "Fix broken button layout in login dialog"

    # 6. Pin trace for Golden Eval
    pin_resp = await async_client.post(
        "/api/v1/system/multimodal-trace/pin/tr_multimodal_001",
        json={"category": "ui_layout_regression"},
    )
    assert pin_resp.status_code == 200
    assert pin_resp.json() == {"ok": True}

    # 7. List traces with pinned_only filter
    list_pinned = await async_client.get("/api/v1/system/multimodal-trace/traces?pinned_only=true")
    assert list_pinned.status_code == 200
    pinned_items = list_pinned.json()
    assert len(pinned_items) == 1
    assert pinned_items[0]["pinned_for_golden_eval"] is True
    assert pinned_items[0]["golden_eval_category"] == "ui_layout_regression"
