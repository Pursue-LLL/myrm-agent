"""
[POS] tests/api/security/test_media_artifact_grants_endpoints.py
[INPUT] fastapi, fastapi.testclient, app.api.security.media_artifact_grants_router
[OUTPUT] Integration tests for Media Artifact Role-Scoped Grants REST endpoints
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.media_artifact_grants_router import (
    router as media_artifact_grants_router,
)
from app.services.security.media_artifact_grants_service import (
    MediaArtifactGrantsService,
    get_media_artifact_grants_service,
)


@pytest.fixture
def client() -> TestClient:
    """Fixture providing isolated TestClient with freshly instantiated service."""
    service = MediaArtifactGrantsService()
    app = FastAPI()
    app.include_router(media_artifact_grants_router)
    app.dependency_overrides[get_media_artifact_grants_service] = lambda: service
    return TestClient(app)


def test_endpoint_evaluate_grant_assistant_and_external(client: TestClient) -> None:
    """Test evaluation endpoint granting assistant and demoting external untrusted origins."""
    # 1. Assistant origin - inline authorized
    resp1 = client.post(
        "/media-artifact-grants/evaluate",
        json={
            "session_id": "sess-test-1",
            "artifact_id": "chart-001",
            "producer_role": "ASSISTANT",
            "mime_type": "image/png",
            "checksum_sha256": "sha256hash1",
            "metadata": {"source": "python_interpreter"},
        },
    )
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert data1["is_allowed"] is True
    assert data1["grant_status"] == "INLINE_RENDER_GRANTED"
    assert data1["rendered_preview_mode"] == "INLINE"

    # 2. External untrusted origin - demoted to safe link
    resp2 = client.post(
        "/media-artifact-grants/evaluate",
        json={
            "session_id": "sess-test-1",
            "artifact_id": "ext-002",
            "producer_role": "EXTERNAL_UNTRUSTED",
            "mime_type": "image/jpeg",
        },
    )
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["is_allowed"] is False
    assert data2["grant_status"] == "UNAUTHORIZED_EXTERNAL"
    assert data2["rendered_preview_mode"] == "SAFE_LINK_ONLY"


def test_endpoint_get_and_list_grants(client: TestClient) -> None:
    """Test retrieving grant records and listing grants for a session."""
    client.post(
        "/media-artifact-grants/evaluate",
        json={
            "session_id": "sess-test-2",
            "artifact_id": "doc-01",
            "producer_role": "TOOL",
            "mime_type": "application/pdf",
        },
    )
    client.post(
        "/media-artifact-grants/evaluate",
        json={
            "session_id": "sess-test-2",
            "artifact_id": "doc-02",
            "producer_role": "USER",
            "mime_type": "text/plain",
        },
    )

    # Specific existing artifact
    get_resp = client.get("/media-artifact-grants/sessions/sess-test-2/artifacts/doc-01")
    assert get_resp.status_code == 200
    assert get_resp.json()["artifact_id"] == "doc-01"
    assert get_resp.json()["is_inline_allowed"] is True

    # Non-existent artifact 404
    not_found = client.get("/media-artifact-grants/sessions/sess-test-2/artifacts/non-existent")
    assert not_found.status_code == 404

    # List all session artifacts
    list_resp = client.get("/media-artifact-grants/sessions/sess-test-2")
    assert list_resp.status_code == 200
    items = list_resp.json()
    assert len(items) == 2


def test_endpoint_revoke_grant(client: TestClient) -> None:
    """Test revoking an existing grant."""
    client.post(
        "/media-artifact-grants/evaluate",
        json={
            "session_id": "sess-test-3",
            "artifact_id": "image-01",
            "producer_role": "ASSISTANT",
            "mime_type": "image/webp",
        },
    )

    revoke_resp = client.post(
        "/media-artifact-grants/revoke",
        json={
            "session_id": "sess-test-3",
            "artifact_id": "image-01",
            "reason": "Security policy update",
        },
    )
    assert revoke_resp.status_code == 200
    assert revoke_resp.json()["revoked"] is True

    # Verify status changed to REVOKED
    get_resp = client.get("/media-artifact-grants/sessions/sess-test-3/artifacts/image-01")
    assert get_resp.status_code == 200
    assert get_resp.json()["is_inline_allowed"] is False
    assert get_resp.json()["grant_status"] == "REVOKED"


def test_endpoint_metrics(client: TestClient) -> None:
    """Test retrieving grant operational metrics."""
    client.post(
        "/media-artifact-grants/evaluate",
        json={
            "session_id": "sess-test-4",
            "artifact_id": "img-01",
            "producer_role": "ASSISTANT",
            "mime_type": "image/png",
        },
    )
    client.post(
        "/media-artifact-grants/evaluate",
        json={
            "session_id": "sess-test-4",
            "artifact_id": "img-02",
            "producer_role": "EXTERNAL_UNTRUSTED",
            "mime_type": "image/png",
        },
    )

    resp = client.get("/media-artifact-grants/metrics")
    assert resp.status_code == 200
    metrics = resp.json()
    assert metrics["grants_evaluated_total"] == 2
    assert metrics["inline_granted_total"] == 1
    assert metrics["external_blocked_total"] == 1
