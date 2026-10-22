"""Batch import must treat YAML-significant descriptions as plain text in its security preview and confirm gates."""

from __future__ import annotations

import io
import uuid
import zipfile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.skills.batch_import import router
from app.api.skills.evolution.helpers import _get_skill_store
from app.core.skills.store.evolution_store import reset_evolution_skill_store
from app.core.skills.utils import yaml_scalar

_DESCRIPTIONS = [
    "Deploy a service: nginx on Ubuntu",
    "key: value # trailing comment",
    "- starts like a list item",
    "[draft] {template} rendering",
]


def _zip_with_quoted_description(name: str, description: str) -> bytes:
    skill_md = f"---\nname: {name}\ndescription: {yaml_scalar(description)}\n---\nprint('ok')\n"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(f"{name}/SKILL.md", skill_md)
    return buffer.getvalue()


@pytest.mark.parametrize("description", _DESCRIPTIONS)
def test_preview_and_confirm_accept_a_description_that_is_valid_yaml_text(description: str) -> None:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/skills")
    client = TestClient(app)
    name = f"yaml-desc-{uuid.uuid4().hex[:8]}"

    preview = client.post(
        "/api/v1/skills/batch-import/preview",
        files={"file": ("skills.zip", _zip_with_quoted_description(name, description), "application/zip")},
    )

    assert preview.status_code == 200
    payload = preview.json()
    assert payload["total_found"] == 1
    item = payload["items"][0]
    assert item["description"] == description
    assert item["security_issues"] is None

    confirm = client.post(
        "/api/v1/skills/batch-import/confirm",
        json={
            "session_id": payload["session_id"],
            "items": [
                {
                    "virtual_id": item["virtual_id"],
                    "name": name,
                    "description": description,
                    "resolution": "new",
                    "existing_skill_id": None,
                }
            ],
        },
    )

    try:
        assert confirm.status_code == 200
        assert confirm.json()["imported_count"] == 1
        assert any(record.name == name for record in _get_skill_store().get_active_skills())
    finally:
        reset_evolution_skill_store()
