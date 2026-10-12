"""Tests for ASR Privacy Tradeoff API endpoints."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.asr_privacy_tradeoff_router import (
    router as asr_privacy_tradeoff_router,
)


@pytest.fixture
def test_client() -> TestClient:
    app = FastAPI()
    app.include_router(asr_privacy_tradeoff_router, prefix="/api/v1/security")
    return TestClient(app)


def test_evaluate_audio_policy_ephemeral(test_client: TestClient) -> None:
    resp = test_client.post(
        "/api/v1/security/asr-privacy-tradeoff/evaluate-policy",
        json={
            "retention_policy": "ephemeral_transcript_only",
            "user_confirmed": True,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["raw_audio_purged"] is True
    assert data["speaker_capability"] == "disabled_no_speaker_data"
    assert "Raw audio is destroyed immediately" in data["tradeoff_warning"]


def test_process_cleanup_endpoint(test_client: TestClient) -> None:
    resp = test_client.post(
        "/api/v1/security/asr-privacy-tradeoff/process-cleanup",
        json={
            "job_id": "job-asr-999",
            "audio_bytes_length": 65536,
            "retention_policy": "retain_voice_embeddings_only",
            "consent_given": True,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["raw_audio_purged"] is True
    assert data["speaker_capability"] == "embeddings_only"
    assert (
        "Raw recording is destroyed, but mathematical speaker embeddings"
        in data["tradeoff_warning"]
    )
