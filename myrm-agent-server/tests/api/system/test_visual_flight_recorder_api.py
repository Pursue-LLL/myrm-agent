"""
[INPUT]:
- httpx, ASGITransport
- app.api.system.visual_flight_recorder_api::router

[OUTPUT]:
- Pytest verification for rolling ring-buffer visual flight recorder and failure slice playback REST endpoints.

[POS]:
tests/api/system/test_visual_flight_recorder_api.py — 视觉故障黑匣子录制与切片回放 API 单元测试。
"""

from collections.abc import AsyncGenerator

from fastapi import FastAPI
import httpx
from httpx import ASGITransport
import pytest

from app.api.system.visual_flight_recorder_api import router as vfr_router

test_app = FastAPI()
test_app.include_router(vfr_router, prefix="/api/v1/system")


@pytest.fixture
async def async_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://testserver",
        headers={"Content-Type": "application/json"},
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_visual_flight_recorder_api_flow(async_client: httpx.AsyncClient) -> None:
    # 1. Reset recorder
    reset_resp = await async_client.post("/api/v1/system/visual-flight-recorder/reset")
    assert reset_resp.status_code == 200
    assert reset_resp.json() == {"ok": True}

    # 2. Check initial status
    stuck_resp = await async_client.get("/api/v1/system/visual-flight-recorder/stuck-status")
    assert stuck_resp.status_code == 200
    stuck_data = stuck_resp.json()
    assert stuck_data["is_stuck"] is False
    assert stuck_data["current_buffer_size"] == 0

    # 3. Push visual frames
    for i in range(5):
        push_resp = await async_client.post(
            "/api/v1/system/visual-flight-recorder/push-frame",
            json={
                "frame": {
                    "frame_index": i,
                    "timestamp_ms": 1719000000000 + i * 200,
                    "image_data_uri": f"data:image/png;base64,frame_content_{i}",
                    "width": 1280,
                    "height": 720,
                    "dom_event_summary": f"user_click_button_{i}",
                }
            },
        )
        assert push_resp.status_code == 200
        assert push_resp.json() == {"ok": True}

    # 4. Capture a failure slice
    capture_resp = await async_client.post(
        "/api/v1/system/visual-flight-recorder/capture-slice",
        json={
            "trace_id": "tr-checkout-err-9",
            "session_id": "sess-user-88",
            "failure_kind": "popup_overlay",
            "root_cause_label": "Cookie consent modal blocked primary submit button",
            "animated_preview_uri": "data:image/webp;base64,mock_preview_anim",
            "custom_slice_id": "vslice-cookie-block",
        },
    )
    assert capture_resp.status_code == 200
    slice_data = capture_resp.json()
    assert slice_data["slice_id"] == "vslice-cookie-block"
    assert slice_data["total_frames"] == 5
    assert slice_data["failure_kind"] == "popup_overlay"
    assert len(slice_data["frames"]) == 5
    assert slice_data["duration_seconds"] == pytest.approx(0.8)

    # 5. Fetch slice by ID
    get_resp = await async_client.get("/api/v1/system/visual-flight-recorder/slice/vslice-cookie-block")
    assert get_resp.status_code == 200
    assert get_resp.json()["slice_id"] == "vslice-cookie-block"

    # 6. Fetch non-existent slice returns 404
    not_found = await async_client.get("/api/v1/system/visual-flight-recorder/slice/non-existent-id")
    assert not_found.status_code == 404

    # 7. List slices with filter
    list_resp = await async_client.get(
        "/api/v1/system/visual-flight-recorder/slices",
        params={"failure_kind": "popup_overlay"},
    )
    assert list_resp.status_code == 200
    slices = list_resp.json()
    assert len(slices) == 1
    assert slices[0]["slice_id"] == "vslice-cookie-block"

    # 8. Reset and verify clear
    reset_again = await async_client.post("/api/v1/system/visual-flight-recorder/reset")
    assert reset_again.status_code == 200
    empty_list = await async_client.get("/api/v1/system/visual-flight-recorder/slices")
    assert len(empty_list.json()) == 0
