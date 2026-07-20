from __future__ import annotations

import io
import uuid
import zipfile

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.skills.batch_import import router
from app.api.skills.evolution.helpers import _get_skill_store


def _make_client() -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/skills")
    return TestClient(app)


def _build_zip_with_skill(skill_dir: str, *, name: str, description: str, content: str) -> bytes:
    buffer = io.BytesIO()
    skill_md = f"---\nname: {name}\ndescription: {description}\n---\n{content}\n"
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(f"{skill_dir}/SKILL.md", skill_md)
    return buffer.getvalue()


def _build_zip_without_skill_md(skill_dir: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(f"{skill_dir}/README.txt", "not a skill")
    return buffer.getvalue()


def test_batch_import_preview_returns_empty_payload_when_zip_contains_no_skill_md() -> None:
    client = _make_client()
    zip_bytes = _build_zip_without_skill_md("no-skill")

    response = client.post(
        "/api/v1/skills/batch-import/preview",
        files={"file": ("skills.zip", zip_bytes, "application/zip")},
    )

    assert response.status_code == 200
    assert response.json() == {
        "session_id": "",
        "items": [],
        "total_found": 0,
        "total_conflicts": 0,
    }


def test_batch_import_confirm_missing_session_returns_structured_detail() -> None:
    client = _make_client()
    missing_session = f"missing-{uuid.uuid4().hex}"

    response = client.post(
        "/api/v1/skills/batch-import/confirm",
        json={
            "session_id": missing_session,
            "items": [
                {
                    "virtual_id": "import_0",
                    "name": "missing-session-skill",
                    "description": "desc",
                    "resolution": "new",
                    "existing_skill_id": None,
                }
            ],
        },
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert isinstance(detail, dict)
    assert set(detail.keys()) == {"message", "error_code"}
    assert detail["error_code"] == ""
    assert "Session" in detail["message"]


def test_batch_import_preview_then_confirm_succeeds_on_real_zip_flow() -> None:
    client = _make_client()
    skill_name = f"integration-skill-{uuid.uuid4().hex[:8]}"
    zip_bytes = _build_zip_with_skill(
        "integration-skill",
        name=skill_name,
        description="integration test",
        content="print('integration')",
    )

    preview = client.post(
        "/api/v1/skills/batch-import/preview",
        files={"file": ("skills.zip", zip_bytes, "application/zip")},
    )
    assert preview.status_code == 200
    preview_payload = preview.json()
    assert preview_payload["total_found"] == 1
    assert preview_payload["total_conflicts"] == 0

    confirm = client.post(
        "/api/v1/skills/batch-import/confirm",
        json={
            "session_id": preview_payload["session_id"],
            "items": [
                {
                    "virtual_id": preview_payload["items"][0]["virtual_id"],
                    "name": skill_name,
                    "description": "integration test",
                    "resolution": "new",
                    "existing_skill_id": None,
                }
            ],
        },
    )

    assert confirm.status_code == 200
    assert confirm.json() == {
        "imported_count": 1,
        "skipped_count": 0,
    }

    store = _get_skill_store()
    try:
        assert any(record.name == skill_name for record in store.get_active_skills())
    finally:
        store.close()


def test_batch_import_confirm_invalid_virtual_id_returns_structured_detail() -> None:
    client = _make_client()
    zip_bytes = _build_zip_with_skill(
        "integration-skill",
        name=f"virtual-id-{uuid.uuid4().hex[:8]}",
        description="integration test",
        content="print('integration')",
    )
    preview = client.post(
        "/api/v1/skills/batch-import/preview",
        files={"file": ("skills.zip", zip_bytes, "application/zip")},
    )
    preview_payload = preview.json()

    response = client.post(
        "/api/v1/skills/batch-import/confirm",
        json={
            "session_id": preview_payload["session_id"],
            "items": [
                {
                    "virtual_id": "bad_virtual_id",
                    "name": "invalid-virtual-id",
                    "description": "integration test",
                    "resolution": "new",
                    "existing_skill_id": None,
                }
            ],
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == {
        "message": "非法的 virtual_id",
        "error_code": "",
    }
