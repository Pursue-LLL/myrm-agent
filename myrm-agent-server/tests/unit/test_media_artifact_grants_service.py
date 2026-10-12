"""
[POS] tests/unit/test_media_artifact_grants_service.py
[INPUT] app.schemas.media_artifact_grants, app.services.security.media_artifact_grants_service
[OUTPUT] Unit tests for MediaArtifactGrantsService
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from app.schemas.media_artifact_grants import (
    EvaluateGrantRequestDTO,
    RevokeGrantRequestDTO,
)
from app.services.security.media_artifact_grants_service import (
    MediaArtifactGrantsService,
)


def test_service_evaluate_assistant_and_tool_grants() -> None:
    """Test inline grant authorization for assistant and tool produced artifacts."""
    service = MediaArtifactGrantsService()

    # 1. Assistant origin
    req_assistant = EvaluateGrantRequestDTO(
        session_id="session-alpha",
        artifact_id="art-chart-1",
        producer_role="ASSISTANT",
        mime_type="image/svg+xml",
        checksum_sha256="abc123sha",
        metadata={"generator": "mermaid_renderer"},
    )
    res_assistant = service.evaluate_and_grant(req_assistant)
    assert res_assistant.is_allowed is True
    assert res_assistant.grant_status == "INLINE_RENDER_GRANTED"
    assert res_assistant.rendered_preview_mode == "INLINE"

    # 2. Tool origin
    req_tool = EvaluateGrantRequestDTO(
        session_id="session-alpha",
        artifact_id="art-screenshot-2",
        producer_role="TOOL",
        mime_type="image/png",
    )
    res_tool = service.evaluate_and_grant(req_tool)
    assert res_tool.is_allowed is True
    assert res_tool.grant_status == "INLINE_RENDER_GRANTED"
    assert res_tool.rendered_preview_mode == "INLINE"


def test_service_evaluate_user_and_external_grants() -> None:
    """Test safe demotion to download-only links for user and untrusted external payloads."""
    service = MediaArtifactGrantsService()

    # 1. User origin
    res_user = service.evaluate_and_grant(
        EvaluateGrantRequestDTO(
            session_id="session-beta",
            artifact_id="art-user-doc",
            producer_role="USER",
            mime_type="text/html",
        )
    )
    assert res_user.is_allowed is False
    assert res_user.grant_status == "UNAUTHORIZED_EXTERNAL"
    assert res_user.rendered_preview_mode == "SAFE_LINK_ONLY"

    # 2. External untrusted origin
    res_ext = service.evaluate_and_grant(
        EvaluateGrantRequestDTO(
            session_id="session-beta",
            artifact_id="art-phish-ad",
            producer_role="EXTERNAL_UNTRUSTED",
            mime_type="image/gif",
        )
    )
    assert res_ext.is_allowed is False
    assert res_ext.grant_status == "UNAUTHORIZED_EXTERNAL"

    # 3. Invalid role fallback
    res_fallback = service.evaluate_and_grant(
        EvaluateGrantRequestDTO(
            session_id="session-beta",
            artifact_id="art-unknown",
            producer_role="SOMETHING_BOGUS",
            mime_type="application/pdf",
        )
    )
    assert res_fallback.is_allowed is False
    assert res_fallback.grant_status == "UNAUTHORIZED_EXTERNAL"


def test_service_revoke_and_lookup_grants() -> None:
    """Test grant lifecycle: issuance, query, revocation, and post-revocation query."""
    service = MediaArtifactGrantsService()

    service.evaluate_and_grant(
        EvaluateGrantRequestDTO(
            session_id="session-gamma",
            artifact_id="art-diagram-3",
            producer_role="ASSISTANT",
            mime_type="image/png",
        )
    )

    # Lookup existing grant
    grant = service.get_grant("session-gamma", "art-diagram-3")
    assert grant is not None
    assert grant.is_inline_allowed is True
    assert grant.producer_role == "ASSISTANT"

    # List session grants
    grants = service.list_grants_for_session("session-gamma")
    assert len(grants) == 1
    assert grants[0].artifact_id == "art-diagram-3"

    # Revoke grant
    rev_res = service.revoke_grant(
        RevokeGrantRequestDTO(
            session_id="session-gamma",
            artifact_id="art-diagram-3",
            reason="User flagged suspicious render",
        )
    )
    assert rev_res.revoked is True

    # Lookup revoked grant
    updated = service.get_grant("session-gamma", "art-diagram-3")
    assert updated is not None
    assert updated.is_inline_allowed is False
    assert updated.grant_status == "REVOKED"


def test_service_metrics() -> None:
    """Test metric tracking on evaluation and revocation."""
    service = MediaArtifactGrantsService()

    service.evaluate_and_grant(
        EvaluateGrantRequestDTO(
            session_id="session-delta",
            artifact_id="art-1",
            producer_role="ASSISTANT",
            mime_type="image/png",
        )
    )
    service.evaluate_and_grant(
        EvaluateGrantRequestDTO(
            session_id="session-delta",
            artifact_id="art-2",
            producer_role="USER",
            mime_type="image/jpeg",
        )
    )
    service.revoke_grant(
        RevokeGrantRequestDTO(
            session_id="session-delta",
            artifact_id="art-1",
        )
    )

    metrics = service.get_metrics()
    assert metrics.grants_evaluated_total == 2
    assert metrics.inline_granted_total == 1
    assert metrics.external_blocked_total == 1
    assert metrics.grants_revoked_total == 1
