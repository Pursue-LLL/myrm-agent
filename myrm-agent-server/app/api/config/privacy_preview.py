"""Privacy protection dry run: what the model would see for a text under the rules being edited.

[INPUT]
- app.core.security.privacy_settings::resolve_privacy_params, privacy_policy_from_params (POS: Business-layer reader of the persisted personal settings for privacy protection.)
- myrm_agent_harness.api.security::preview_privacy_policy (POS: Dry run of the privacy layer for a settings page: what the model would see for a text, with nothing recorded.)

[OUTPUT]
- privacy_preview_router: FastAPI APIRouter mounting POST /privacy-preview
- PrivacyPreviewRequest, PrivacyPreviewResponse: Pydantic request and response models

[POS]
app/api/config/privacy_preview.py - lets the privacy settings page try a sentence against the rules as they stand in
the form, before or without saving. The rules arrive in the request, like those of a chat turn, and the harness answers
as a turn would, so the page shows what the product does rather than what a second implementation guesses. The answer
also names the custom patterns that cannot match, which is why an empty sentence is accepted: the page asks for them as
soon as there are rules, without waiting for a sentence. Nothing is stored or logged.
"""

from __future__ import annotations

from fastapi import APIRouter
from myrm_agent_harness.agent.security.types import PIIAction, SensitivityLevel
from myrm_agent_harness.api.security import preview_privacy_policy
from pydantic import BaseModel, Field

from app.core.security.privacy_settings import (
    PrivacyAgentParams,
    privacy_policy_from_params,
    resolve_privacy_params,
)

privacy_preview_router = APIRouter(tags=["privacy"])

_MAX_TEXT_CHARS = 4000


class PrivacyPreviewRequest(BaseModel):
    """A sentence to try and the rules to try it against; an action left out takes the product default.

    The rule lists are not capped: a chat turn accepts every rule the settings hold, so the preview must too.
    """

    text: str = Field(max_length=_MAX_TEXT_CHARS)
    privacy_s2_action: PIIAction | None = None
    privacy_s3_action: PIIAction | None = None
    privacy_custom_keywords_s2: list[str] = Field(default_factory=list)
    privacy_custom_keywords_s3: list[str] = Field(default_factory=list)
    privacy_custom_patterns_s2: list[str] = Field(default_factory=list)
    privacy_custom_patterns_s3: list[str] = Field(default_factory=list)

    def privacy_params(self) -> PrivacyAgentParams:
        params: PrivacyAgentParams = {
            "privacy_enabled": True,
            "privacy_custom_keywords_s2": self.privacy_custom_keywords_s2,
            "privacy_custom_keywords_s3": self.privacy_custom_keywords_s3,
            "privacy_custom_patterns_s2": self.privacy_custom_patterns_s2,
            "privacy_custom_patterns_s3": self.privacy_custom_patterns_s3,
        }
        if self.privacy_s2_action is not None:
            params["privacy_s2_action"] = self.privacy_s2_action.value
        if self.privacy_s3_action is not None:
            params["privacy_s3_action"] = self.privacy_s3_action.value
        return params


class PrivacyPreviewResponse(BaseModel):
    """``action`` is null for a text with nothing sensitive; ``model_sees`` is null when the rules block the text;
    ``ineffective_patterns`` lists the custom patterns that do not compile and so protect nothing."""

    level: SensitivityLevel
    action: PIIAction | None
    model_sees: str | None
    ineffective_patterns: list[str]


@privacy_preview_router.post("/privacy-preview", response_model=PrivacyPreviewResponse)
def preview_privacy(request: PrivacyPreviewRequest) -> PrivacyPreviewResponse:
    """Apply the rules in the request to the text as a chat turn would, with the regex layer only.

    Synchronous on purpose: a pseudonymizing policy opens a throwaway SQLite store, which must not block the event loop.
    """
    policy = privacy_policy_from_params(resolve_privacy_params(None, request.privacy_params()))
    preview = preview_privacy_policy(request.text, policy)
    return PrivacyPreviewResponse(
        level=preview.level,
        action=preview.action,
        model_sees=preview.model_sees,
        ineffective_patterns=list(preview.ineffective_patterns),
    )
