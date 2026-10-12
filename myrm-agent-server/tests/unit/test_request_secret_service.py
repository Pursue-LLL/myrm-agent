"""
[POS] tests/unit/test_request_secret_service.py
[INPUT] app.schemas.request_secret, app.services.security.request_secret_service
[OUTPUT] Unit tests for RequestSecretService
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import pytest

from app.schemas.request_secret import (
    CreateSecretCardRequestDTO,
    FulfillSecretCardRequestDTO,
    RegisterSavedCredentialRequestDTO,
    RejectSecretCardRequestDTO,
    SecretInputSubmissionDTO,
    SecretRequestIntentDTO,
)
from app.services.security.request_secret_service import (
    RequestSecretService,
)


@pytest.fixture
def service() -> RequestSecretService:
    return RequestSecretService()


def test_create_and_fulfill_card_with_plaintext(service: RequestSecretService) -> None:
    # 1. Create card session
    create_req = CreateSecretCardRequestDTO(
        agent_id="agent-worker-01",
        task_id="task-scrape-101",
        intent=SecretRequestIntentDTO(
            target_system="openai",
            purpose_description="Need API key to embed document chunks",
            scope="api_key",
            ttl_seconds=1800,
        ),
    )
    session = service.create_card_session(create_req)

    assert session.card_id.startswith("card-sec-")
    assert session.status == "pending"
    assert session.intent.target_system == "openai"

    # 2. Fulfill with raw secret
    fulfill_req = FulfillSecretCardRequestDTO(
        card_id=session.card_id,
        submission=SecretInputSubmissionDTO(
            raw_secret="sk-live-super-secret-key-11223344",
            extra_metadata={"environment": "staging"},
        ),
    )
    result = service.fulfill_card(fulfill_req)

    assert result.card_id == session.card_id
    assert result.target_system == "openai"
    assert result.is_backfill is False
    assert result.stored_safely is True
    assert "sk-****3344" in result.mask_preview
    assert "sk-live-super-secret-key" not in result.transcript_safe_summary
    assert "sk-****3344" in result.transcript_safe_summary

    # 3. Query card state
    queried = service.get_card_session(session.card_id)
    assert queried is not None
    assert queried.status == "fulfilled"
    assert queried.masked_ref is not None
    assert queried.masked_ref.mask_preview == result.mask_preview


def test_fulfill_card_with_saved_credential_backfill(
    service: RequestSecretService,
) -> None:
    # 1. Register saved credential
    reg_req = RegisterSavedCredentialRequestDTO(
        target_system="github",
        raw_secret="ghp_abcdef1234567890abcdef1234567890",
    )
    saved_ref = service.register_saved_credential(reg_req)
    assert saved_ref.target_system == "github"
    assert saved_ref.mask_preview.startswith("ghp_****")

    # 2. Agent creates request card
    create_req = CreateSecretCardRequestDTO(
        agent_id="agent-git-01",
        task_id="task-clone-repo",
        intent=SecretRequestIntentDTO(
            target_system="github",
            purpose_description="Sync private submodules",
        ),
    )
    card = service.create_card_session(create_req)

    # 3. User backfills using saved credential
    fulfill_req = FulfillSecretCardRequestDTO(
        card_id=card.card_id,
        submission=SecretInputSubmissionDTO(
            selected_credential_id=saved_ref.credential_id,
        ),
    )
    result = service.fulfill_card(fulfill_req)

    assert result.is_backfill is True
    assert result.target_system == "github"
    assert result.mask_preview == saved_ref.mask_preview


def test_reject_card(service: RequestSecretService) -> None:
    create_req = CreateSecretCardRequestDTO(
        agent_id="agent-01",
        task_id="task-01",
        intent=SecretRequestIntentDTO(
            target_system="aws",
            purpose_description="Access S3 bucket",
        ),
    )
    card = service.create_card_session(create_req)

    reject_req = RejectSecretCardRequestDTO(
        card_id=card.card_id,
        reason="Security audit policy denial",
    )
    rejected = service.reject_card(reject_req)

    assert rejected.status == "rejected"
    assert rejected.rejection_reason == "Security audit policy denial"


def test_register_and_list_saved_credentials(service: RequestSecretService) -> None:
    service.register_saved_credential(
        RegisterSavedCredentialRequestDTO(target_system="slack", raw_secret="xoxb-1122334455-667788")
    )
    service.register_saved_credential(
        RegisterSavedCredentialRequestDTO(target_system="jira", raw_secret="jira-api-token-998877")
    )

    all_creds = service.list_saved_credentials()
    assert len(all_creds) >= 2

    slack_creds = service.list_saved_credentials(target_system="slack")
    assert len(slack_creds) == 1
    assert slack_creds[0].target_system == "slack"
