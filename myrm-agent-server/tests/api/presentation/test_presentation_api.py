import io

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pptx import Presentation

from app.api.presentation.routes import router as presentation_router


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(presentation_router, prefix="/api/v1/presentation")
    return TestClient(app)


def test_generate_presentation_success(client: TestClient) -> None:
    payload = {
        "topic": "多智能体协同研发架构",
        "template_style": "enterprise_blue",
        "slides_count": 5,
        "enable_illustrations": True,
    }

    response = client.post("/api/v1/presentation/generate", json=payload)
    assert response.status_code == 201

    data = response.json()
    assert data["topic"] == "多智能体协同研发架构"
    assert data["template_style"] == "enterprise_blue"
    assert data["total_slides"] == 5
    assert len(data["slides"]) == 5
    assert data["file_size_bytes"] > 0
    assert "download_url" in data
    assert data["id"].startswith("pres_")

    # Verify first slide is title_hero
    assert data["slides"][0]["layout"] == "title_hero"
    assert data["slides"][0]["slide_number"] == 1


def test_get_presentation_metadata(client: TestClient) -> None:
    # First generate one
    gen_resp = client.post(
        "/api/v1/presentation/generate",
        json={"topic": "全栈工程效能演进", "template_style": "minimal_dark", "slides_count": 4},
    )
    assert gen_resp.status_code == 201
    artifact_id = gen_resp.json()["id"]

    # Then query by ID
    get_resp = client.get(f"/api/v1/presentation/{artifact_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == artifact_id
    assert get_resp.json()["topic"] == "全栈工程效能演进"

    # Query nonexistent ID
    not_found_resp = client.get("/api/v1/presentation/nonexistent_id_999")
    assert not_found_resp.status_code == 404


def test_download_presentation_pptx_binary(client: TestClient) -> None:
    gen_resp = client.post(
        "/api/v1/presentation/generate",
        json={"topic": "企业级云原生微服务", "template_style": "tech_emerald", "slides_count": 4},
    )
    assert gen_resp.status_code == 201
    artifact_id = gen_resp.json()["id"]

    # Download binary .pptx
    dl_resp = client.get(f"/api/v1/presentation/{artifact_id}/download")
    assert dl_resp.status_code == 200
    assert "presentationml.presentation" in dl_resp.headers["content-type"]
    assert len(dl_resp.content) > 1000

    # Verify the downloaded binary can be parsed validly by python-pptx
    prs = Presentation(io.BytesIO(dl_resp.content))
    assert len(prs.slides) == 4
