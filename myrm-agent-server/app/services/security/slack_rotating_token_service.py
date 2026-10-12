"""Service layer for Slack Rotating Token Classification and Scope Inspection.

[INPUT]
- ClassifySlackTokenRequest, InspectSlackScopeRequest DTOs.

[OUTPUT]
- ClassifySlackTokenResponse, InspectSlackScopeResponse DTOs.

[POS]
- Server service encapsulating OpenConnector #14c3a6c Slack rotating token recognition.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.core.security.slack_rotating_token import (
    SlackScopeInspection,
    SlackScopeInspector,
    SlackTokenClassification,
    SlackTokenClassifier,
    SlackTokenType,
)

from app.schemas.slack_rotating_token import (
    ClassifySlackTokenRequest,
    ClassifySlackTokenResponse,
    InspectSlackScopeRequest,
    InspectSlackScopeResponse,
    SlackTokenCategoryDto,
    SlackTokenTypeDto,
)

logger = logging.getLogger(__name__)


class SlackRotatingTokenService:
    """Service providing Slack access token classification and OAuth scope inspection."""

    def __init__(
        self,
        classifier: SlackTokenClassifier | None = None,
        inspector: SlackScopeInspector | None = None,
    ) -> None:
        self._classifier = classifier or SlackTokenClassifier()
        self._inspector = inspector or SlackScopeInspector()

    def classify_token(
        self,
        request: ClassifySlackTokenRequest,
    ) -> ClassifySlackTokenResponse:
        """Classify a Slack token string or authorization header into its category and type."""
        classification: SlackTokenClassification = self._classifier.classify(
            token_or_auth_header=request.token_or_auth_header,
            raw_token_type_hint=request.raw_token_type_hint,
        )
        return ClassifySlackTokenResponse(
            token_type=SlackTokenTypeDto(classification.token_type.value),
            category=SlackTokenCategoryDto(classification.category.value),
            is_rotating=classification.is_rotating,
            prefix_matched=classification.prefix_matched,
            normalized_token=classification.normalized_token,
            is_bearer_wrapped=classification.is_bearer_wrapped,
        )

    def inspect_scopes(
        self,
        request: InspectSlackScopeRequest,
    ) -> InspectSlackScopeResponse:
        """Inspect and parse OAuth scopes from Slack metadata according to token semantic type."""
        token_type = SlackTokenType(request.token_type.value)
        inspection: SlackScopeInspection = self._inspector.inspect_scopes(
            token_type=token_type,
            metadata=request.metadata,
        )
        return InspectSlackScopeResponse(
            token_type=SlackTokenTypeDto(inspection.token_type.value),
            resolved_scopes=inspection.resolved_scopes,
            source_field=inspection.source_field,
        )


slack_rotating_token_service = SlackRotatingTokenService()
